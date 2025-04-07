"""
Estrategias mejoradas de fallback para el sistema de recomendaciones.

Esta versión incluye la capacidad de excluir productos que el usuario
ya ha visto o añadido al carrito.
"""

import logging
from typing import List, Dict, Optional, Set
import random
from collections import Counter

logger = logging.getLogger(__name__)

class ImprovedFallbackStrategies:
    """
    Implementa estrategias avanzadas de fallback para recomendaciones.
    """
    
    @staticmethod
    async def get_user_interactions(user_id: str, user_events: List[Dict]) -> Set[str]:
        """
        Obtiene el conjunto de IDs de productos con los que el usuario ha interactuado.
        
        Args:
            user_id: ID del usuario
            user_events: Lista de eventos del usuario
            
        Returns:
            Set[str]: Conjunto de IDs de productos con los que el usuario ha interactuado
        """
        interacted_products = set()
        
        if not user_events:
            return interacted_products
            
        for event in user_events:
            if event.get("product_id"):
                interacted_products.add(str(event.get("product_id")))
                
        logger.info(f"Usuario {user_id} ha interactuado con {len(interacted_products)} productos")
        if interacted_products:
            logger.info(f"Productos: {', '.join(list(interacted_products)[:5])}" + 
                      (f"... y {len(interacted_products) - 5} más" if len(interacted_products) > 5 else ""))
        
        return interacted_products
    
    @staticmethod
    async def get_popular_products(
        products: List[Dict], 
        n: int = 5,
        exclude_products: Optional[Set[str]] = None
    ) -> List[Dict]:
        """
        Obtiene productos "populares" basándose en criterios heurísticos
        excluyendo productos con los que el usuario ya ha interactuado.
        
        Args:
            products: Lista de productos disponibles
            n: Número de recomendaciones a devolver
            exclude_products: Conjunto de IDs de productos a excluir
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        if not products:
            logger.warning("No hay productos disponibles para recomendaciones populares")
            return []
        
        # Si no hay productos a excluir, inicializar como conjunto vacío
        if exclude_products is None:
            exclude_products = set()
            
        # Filtrar productos para excluir los que el usuario ya ha interactuado
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
        ]
        
        if not available_products:
            logger.warning("No hay productos disponibles después de excluir las interacciones del usuario")
            # Si no quedan productos después de filtrar, usar todos los productos
            available_products = products
            logger.info("Utilizando todos los productos como fallback")
        
        # Calcular una puntuación de "popularidad" para cada producto
        scored_products = []
        
        for product in available_products:
            score = 0
            
            # Productos con imágenes son más populares
            if product.get("images") and len(product.get("images", [])) > 0:
                score += 2
            
            # Productos con descripción detallada son más populares
            description = product.get("body_html", "") or product.get("description", "")
            if description and len(description) > 100:
                score += 1
            
            # Productos con variantes son más populares
            if product.get("variants") and len(product.get("variants", [])) > 1:
                score += 1
            
            # Productos con precio en un rango medio son más populares
            price = 0
            if product.get("variants") and len(product.get("variants")) > 0:
                price_str = product["variants"][0].get("price", "0")
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    price = 0
            
            # Penalizar productos sin precio o con precio cero
            if price <= 0:
                score -= 1
            # Productos en un rango de precio medio son más populares
            elif 10 <= price <= 100:
                score += 1
            
            # Productos con etiquetas son más populares
            if product.get("tags") and len(product.get("tags", [])) > 0:
                score += 1
            
            # Añadir variación aleatoria para diversidad (±0.5)
            score += random.uniform(-0.5, 0.5)
            
            scored_products.append((product, score))
        
        # Ordenar productos por puntuación de popularidad
        sorted_products = sorted(scored_products, key=lambda x: x[1], reverse=True)
        
        # Tomar los N productos más populares
        popular_products = sorted_products[:min(n, len(sorted_products))]
        
        # Convertir a formato de respuesta
        recommendations = []
        for product, score in popular_products:
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
                "score": score,
                "recommendation_type": "popular_fallback"
            })
        
        logger.info(f"Generadas {len(recommendations)} recomendaciones populares (excluyendo productos vistos)")
        return recommendations
    
    @staticmethod
    async def get_diverse_category_products(
        products: List[Dict], 
        n: int = 5,
        exclude_products: Optional[Set[str]] = None
    ) -> List[Dict]:
        """
        Obtiene productos de diversas categorías para ofrecer variedad,
        excluyendo productos con los que el usuario ya ha interactuado.
        
        Args:
            products: Lista de productos disponibles
            n: Número de recomendaciones a devolver
            exclude_products: Conjunto de IDs de productos a excluir
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        if not products:
            logger.warning("No hay productos disponibles para recomendaciones diversas")
            return []
        
        # Si no hay productos a excluir, inicializar como conjunto vacío
        if exclude_products is None:
            exclude_products = set()
            
        # Filtrar productos para excluir los que el usuario ya ha interactuado
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
        ]
        
        if not available_products:
            logger.warning("No hay productos disponibles después de excluir las interacciones del usuario")
            # Si no quedan productos después de filtrar, usar todos los productos
            available_products = products
            logger.info("Utilizando todos los productos como fallback")
        
        # Agrupar productos por categoría
        products_by_category = {}
        for product in available_products:
            category = product.get("product_type", "General")
            if category not in products_by_category:
                products_by_category[category] = []
            products_by_category[category].append(product)
        
        # Seleccionar productos de diferentes categorías
        diverse_products = []
        categories = list(products_by_category.keys())
        
        # Determinar cuántos productos tomar de cada categoría
        num_categories = min(n, len(categories))
        products_per_category = max(1, n // num_categories)
        
        # Seleccionar categorías y productos
        selected_categories = random.sample(categories, num_categories)
        
        for category in selected_categories:
            category_products = products_by_category[category]
            # Tomar productos aleatorios de esta categoría
            num_to_take = min(products_per_category, len(category_products))
            selected_products = random.sample(category_products, num_to_take)
            diverse_products.extend(selected_products)
        
        # Si necesitamos más productos para alcanzar n
        if len(diverse_products) < n:
            remaining_products = []
            for category in categories:
                if category not in selected_categories:
                    remaining_products.extend(products_by_category[category])
            
            # Seleccionar productos adicionales aleatoriamente
            num_additional = min(n - len(diverse_products), len(remaining_products))
            if num_additional > 0:
                additional_products = random.sample(remaining_products, num_additional)
                diverse_products.extend(additional_products)
        
        # Limitar al número solicitado (por si acaso hemos seleccionado más)
        diverse_products = diverse_products[:n]
        
        # Convertir a formato de respuesta
        recommendations = []
        for product in diverse_products:
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
                "score": 0.5,  # Score fijo para productos diversos
                "recommendation_type": "diverse_fallback"
            })
        
        logger.info(f"Generadas {len(recommendations)} recomendaciones diversas (excluyendo productos vistos)")
        return recommendations
    
    @staticmethod
    async def get_personalized_fallback(
        user_id: str,
        products: List[Dict],
        user_events: Optional[List[Dict]] = None,
        n: int = 5
    ) -> List[Dict]:
        """
        Genera recomendaciones personalizadas fallback basándose en eventos previos
        del usuario si están disponibles, o en heurísticas si no hay datos previos.
        Excluye productos con los que el usuario ya ha interactuado.
        
        Args:
            user_id: ID del usuario
            products: Lista de productos disponibles
            user_events: Lista de eventos previos del usuario (opcional)
            n: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        if not products:
            logger.warning(f"No hay productos disponibles para recomendaciones personalizadas para {user_id}")
            return []
        
        # Obtener productos con los que el usuario ha interactuado
        interacted_products = await ImprovedFallbackStrategies.get_user_interactions(user_id, user_events)
        
        # Si tenemos eventos previos del usuario
        if user_events and len(user_events) > 0:
            logger.info(f"Generando recomendaciones personalizadas para {user_id} basadas en {len(user_events)} eventos")
            
            # Extraer categorías preferidas del usuario
            preferred_categories = []
            product_views = Counter()
            
            for event in user_events:
                product_id = event.get("product_id")
                if product_id:
                    product_views[product_id] += 1
                    
                    # Buscar el producto completo para obtener su categoría
                    for product in products:
                        if str(product.get("id", "")) == product_id:
                            category = product.get("product_type", "General")
                            preferred_categories.append(category)
                            break
            
            # Obtener categorías más frecuentes
            category_counts = Counter(preferred_categories)
            top_categories = [category for category, _ in category_counts.most_common(3)]
            
            if top_categories:
                logger.info(f"Categorías preferidas para usuario {user_id}: {top_categories}")
                
                # Seleccionar productos de las categorías preferidas
                preferred_products = []
                
                for category in top_categories:
                    category_products = [
                        p for p in products 
                        if p.get("product_type", "General") == category
                        and str(p.get("id", "")) not in interacted_products  # Excluir productos ya vistos
                    ]
                    
                    if category_products:
                        # Tomar hasta n/len(top_categories) productos de cada categoría
                        products_per_category = max(1, n // len(top_categories))
                        num_to_take = min(products_per_category, len(category_products))
                        selected = random.sample(category_products, num_to_take)
                        preferred_products.extend(selected)
                
                # Si no tenemos suficientes productos, añadir algunos aleatorios
                if len(preferred_products) < n:
                    # Excluir productos ya seleccionados y vistos
                    selected_ids = set(str(p.get("id", "")) for p in preferred_products)
                    remaining_products = [
                        p for p in products 
                        if str(p.get("id", "")) not in selected_ids
                        and str(p.get("id", "")) not in interacted_products
                    ]
                    
                    num_additional = min(n - len(preferred_products), len(remaining_products))
                    if num_additional > 0:
                        additional_products = random.sample(remaining_products, num_additional)
                        preferred_products.extend(additional_products)
                
                # Limitar al número solicitado
                personalized_products = preferred_products[:n]
                
                # Si aún no tenemos suficientes productos, usar productos populares
                if len(personalized_products) < n:
                    logger.info(f"No hay suficientes productos en las categorías preferidas, usando populares")
                    return await ImprovedFallbackStrategies.get_popular_products(
                        products, 
                        n,
                        exclude_products=interacted_products
                    )
            else:
                # Si no hay categorías preferidas, usar productos populares
                logger.info(f"No se identificaron categorías preferidas, usando populares")
                return await ImprovedFallbackStrategies.get_popular_products(
                    products, 
                    n,
                    exclude_products=interacted_products
                )
        else:
            logger.info(f"No hay eventos previos para usuario {user_id}, usando fallback diverso")
            return await ImprovedFallbackStrategies.get_diverse_category_products(
                products, 
                n,
                exclude_products=interacted_products
            )
        
        # Convertir a formato de respuesta
        recommendations = []
        for i, product in enumerate(personalized_products):
            # Extraer precio del primer variante si está disponible
            price = 0.0
            if product.get("variants") and len(product["variants"]) > 0:
                price_str = product["variants"][0].get("price", "0")
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    price = 0.0
            
            # Dar mayor score a los primeros productos (de categorías más preferidas)
            score = 0.9 - (i * 0.05)  # Empieza en 0.9 y va disminuyendo
            score = max(0.5, score)   # No bajar de 0.5
            
            recommendations.append({
                "id": str(product.get("id", "")),
                "title": product.get("title", ""),
                "description": product.get("body_html", "").replace("<p>", "").replace("</p>", ""),
                "price": price,
                "category": product.get("product_type", ""),
                "score": score,
                "recommendation_type": "personalized_fallback"
            })
        
        logger.info(f"Generadas {len(recommendations)} recomendaciones personalizadas para {user_id}")
        return recommendations
    
    @staticmethod
    async def smart_fallback(
        user_id: str,
        products: List[Dict],
        user_events: Optional[List[Dict]] = None,
        n: int = 5
    ) -> List[Dict]:
        """
        Estrategia de fallback inteligente que selecciona la mejor
        estrategia basada en el contexto y excluye productos ya vistos.
        
        Args:
            user_id: ID del usuario
            products: Lista de productos disponibles
            user_events: Lista de eventos previos del usuario (opcional)
            n: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        # Obtener productos con los que el usuario ha interactuado
        interacted_products = await ImprovedFallbackStrategies.get_user_interactions(user_id, user_events)
        
        # Si tenemos eventos del usuario, usar recomendaciones personalizadas
        if user_events and len(user_events) > 0:
            logger.info(f"Usando fallback personalizado para usuario {user_id} con {len(user_events)} eventos")
            return await ImprovedFallbackStrategies.get_personalized_fallback(user_id, products, user_events, n)
        
        # Si es un usuario nuevo, alternar entre productos populares y diversos
        random_choice = random.random()
        if random_choice < 0.7:  # 70% del tiempo usar productos populares
            logger.info(f"Usando fallback popular para usuario {user_id}")
            return await ImprovedFallbackStrategies.get_popular_products(
                products, 
                n, 
                exclude_products=interacted_products
            )
        else:  # 30% del tiempo usar productos diversos para descubrimiento
            logger.info(f"Usando fallback diverso para usuario {user_id}")
            return await ImprovedFallbackStrategies.get_diverse_category_products(
                products, 
                n, 
                exclude_products=interacted_products
            )
