"""
Estrategias mejoradas de fallback para el sistema de recomendaciones.

Esta versión incluye la capacidad de excluir productos que el usuario
ya ha visto o añadido al carrito, Y DETECCIÓN DE CATEGORÍA DESDE LA QUERY DEL USUARIO.

✨ MEJORA FASE 3B: Query-aware category detection
"""

import logging
from typing import List, Dict, Optional, Set
import random
from collections import Counter
import re

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# ✨ NUEVA FUNCIONALIDAD: Mapeo de palabras clave a categorías
# ═══════════════════════════════════════════════════════════════════════════

# Mapeo de keywords en español e inglés a categorías del catálogo
CATEGORY_KEYWORDS = {
    "ZAPATOS": [
        "zapato", "zapatos", "shoe", "shoes", "calzado", "footwear",
        "sandalia", "sandalias", "sandal", "sandals",
        "bota", "botas", "boot", "boots",
        "tenis", "sneaker", "sneakers"
    ],
    "VESTIDOS LARGOS": [
        "vestido largo", "vestidos largos", "long dress", "maxi dress",
        "vestido de noche", "evening dress", "gala"
    ],
    "VESTIDOS CORTOS": [
        "vestido corto", "vestidos cortos", "short dress", "mini dress",
        "vestido casual"
    ],
    "VESTIDOS MIDIS": [
        "vestido midi", "vestidos midis", "midi dress",
        "vestido medio", "medium dress"
    ],
    "PANTALONES": [
        "pantalon", "pantalones", "pants", "trousers",
        "jean", "jeans", "vaquero"
    ],
    "FALDAS": [
        "falda", "faldas", "skirt", "skirts"
    ],
    "TOPS": [
        "top", "tops", "blusa", "blusas", "blouse", "camisa", "camisas", "shirt"
    ],
    "BRALETTES": [
        "bralette", "bralettes", "sostén", "sujetador", "bra"
    ],
    "LENCERIA": [
        "lenceria", "lencería", "lingerie", "ropa interior", "underwear"
    ],
    "ACCESSORIES": [
        "accesorio", "accesorios", "accessory", "accessories",
        "complemento", "complementos"
    ],
    "CLUTCH": [
        "clutch", "bolso", "bolsos", "bag", "bags", "cartera", "carteras", "purse"
    ],
    "BRAZALETES": [
        "brazalete", "brazaletes", "pulsera", "pulseras", "bracelet", "bracelets"
    ],
    "COLLARES": [
        "collar", "collares", "necklace", "necklaces"
    ],
    "AROS": [
        "aro", "aros", "pendiente", "pendientes", "earring", "earrings", "aretes"
    ],
    "CINTURONES": [
        "cinturon", "cinturones", "belt", "belts"
    ],
    "CHAQUETAS": [
        "chaqueta", "chaquetas", "jacket", "jackets", "abrigo", "coat"
    ],
    "KIMONOS": [
        "kimono", "kimonos"
    ],
    "CAPAS BORDADAS": [
        "capa bordada", "capas bordadas", "embroidered cape"
    ],
    "CAPAS GASA": [
        "capa gasa", "capas gasa", "chiffon cape"
    ],
    "ENTERITOS LARGOS": [
        "enterito largo", "enteritos largos", "jumpsuit", "long jumpsuit"
    ],
    "ENTERITOS CORTOS": [
        "enterito corto", "enteritos cortos", "short jumpsuit", "romper"
    ],
    "PIJAMAS": [
        "pijama", "pijamas", "pajamas", "sleepwear"
    ],
    "NOVIAS LARGOS": [
        "vestido novia largo", "wedding dress", "bride dress long",
        "traje novia", "novia", "boda largo"
    ],
    "NOVIAS CORTOS": [
        "vestido novia corto", "short wedding dress", "bride dress short",
        "boda corto"
    ],
    "NOVIAS MIDIS": [
        "vestido novia midi", "midi wedding dress", "bride dress midi",
        "boda midi"
    ]
}


def extract_category_from_query(query: str, available_categories: Set[str]) -> Optional[str]:
    """
    Extrae la categoría mencionada en la query del usuario.
    
    Usa un mapeo de palabras clave para detectar categorías específicas,
    priorizando coincidencias exactas de múltiples palabras sobre palabras individuales.
    
    Args:
        query: Query del usuario en lenguaje natural
        available_categories: Set de categorías disponibles en el catálogo
        
    Returns:
        str: Nombre de la categoría detectada o None si no se detecta ninguna
        
    Examples:
        >>> extract_category_from_query("necesito zapatos formales", {"ZAPATOS", "VESTIDOS"})
        'ZAPATOS'
        
        >>> extract_category_from_query("vestido largo para boda", {"VESTIDOS LARGOS"})
        'VESTIDOS LARGOS'
        
        >>> extract_category_from_query("algo elegante", {"ZAPATOS", "VESTIDOS"})
        None
    """
    if not query:
        return None
    
    # Normalizar query: lowercase y remover acentos básicos
    query_lower = query.lower()
    query_normalized = query_lower.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    
    # Trackear coincidencias con su longitud (para priorizar frases largas)
    matches = []
    
    # Iterar sobre cada categoría en el mapeo
    for category, keywords in CATEGORY_KEYWORDS.items():
        # Solo considerar categorías que existen en el catálogo
        if category not in available_categories:
            continue
            
        # Buscar cada keyword en la query
        for keyword in keywords:
            keyword_normalized = keyword.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
            
            # Buscar coincidencia de palabra completa (no substring)
            # Ejemplo: "zapato" no debe matchear "zapatería"
            pattern = r'\b' + re.escape(keyword_normalized) + r'\b'
            if re.search(pattern, query_normalized):
                # Agregar match con longitud del keyword (más largo = más específico)
                matches.append((category, len(keyword)))
                logger.debug(f"🔍 Query keyword match: '{keyword}' → {category}")
    
    if not matches:
        logger.debug(f"🔍 No category detected in query: '{query}'")
        return None
    
    # Priorizar coincidencia más larga (más específica)
    # Ejemplo: "vestido largo" (2 palabras) > "vestido" (1 palabra)
    best_match = max(matches, key=lambda x: x[1])
    detected_category = best_match[0]
    
    logger.info(f"🎯 Category detected from query: '{detected_category}' (from query: '{query[:50]}...')")
    return detected_category


# ═══════════════════════════════════════════════════════════════════════════
# Funciones de utilidad (sin cambios)
# ═══════════════════════════════════════════════════════════════════════════

def safe_clean_text(text: Optional[str], field_name: str = "text") -> str:
    """
    Limpia texto de forma segura manejando valores None explícitos.
    """
    try:
        if text is None:
            logger.debug(f"Campo {field_name} es None, usando string vacío")
            return ""
        
        if not isinstance(text, str):
            logger.debug(f"Campo {field_name} no es string, convirtiendo: {type(text)}")
            text = str(text)
        
        cleaned = text.replace("<p>", "").replace("</p>", "")
        cleaned = cleaned.replace("<br>", " ").replace("<br/>", " ")
        cleaned = cleaned.replace("<div>", "").replace("</div>", "")
        cleaned = " ".join(cleaned.split())
        
        return cleaned
        
    except Exception as e:
        logger.warning(f"Error limpiando texto en campo {field_name}: {e}")
        return ""

def safe_extract_price(product: Dict) -> float:
    """
    Extrae precio de forma segura de un producto.
    """
    try:
        if product.get("variants") and len(product["variants"]) > 0:
            price_str = product["variants"][0].get("price", "0")
            if price_str is not None:
                return float(price_str)
        
        price = product.get("price", 0.0)
        if price is not None:
            if isinstance(price, str):
                return float(price)
            return float(price)
        
        return 0.0
        
    except (ValueError, TypeError, IndexError) as e:
        logger.debug(f"Error extrayendo precio del producto {product.get('id', 'unknown')}: {e}")
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Clase principal con estrategias de fallback
# ═══════════════════════════════════════════════════════════════════════════

class ImprovedFallbackStrategies:
    """
    Implementa estrategias avanzadas de fallback para recomendaciones.
    ✨ MEJORADO: Ahora con detección de categoría desde query del usuario.
    """
    
    @staticmethod
    async def get_user_interactions(user_id: str, user_events: List[Dict]) -> Set[str]:
        """
        Obtiene el conjunto de IDs de productos con los que el usuario ha interactuado.
        """
        interacted_products = set()
        
        if not user_events:
            return interacted_products
            
        for event in user_events:
            product_id = event.get("productId") or event.get("product_id")
            if product_id:
                interacted_products.add(str(product_id))
                
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
        """
        if not products:
            logger.warning("No hay productos disponibles para recomendaciones populares")
            return []
        
        if exclude_products is None:
            exclude_products = set()
            
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
        ]
        
        if not available_products:
            logger.warning("No hay productos disponibles después de excluir las interacciones del usuario")
            if len(products) > len(exclude_products):
                available_products = [p for p in products if str(p.get("id", "")) not in exclude_products]
            else:
                available_products = products[:min(n, len(products))]
            logger.info(f"Utilizando {len(available_products)} productos como fallback")
        
        scored_products = []
        
        for product in available_products:
            score = 0
            
            if product.get("images") and len(product.get("images", [])) > 0:
                score += 2
            
            description = product.get("body_html", "") or product.get("description", "")
            if description and len(description) > 100:
                score += 1
            
            if product.get("variants") and len(product.get("variants", [])) > 1:
                score += 1
            
            price = 0
            if product.get("variants") and len(product.get("variants")) > 0:
                price_str = product["variants"][0].get("price", "0")
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    price = 0
            
            if price <= 0:
                score -= 1
            elif 10 <= price <= 100:
                score += 1
            
            if product.get("tags") and len(product.get("tags", [])) > 0:
                score += 1
            
            score += random.uniform(-0.5, 0.5)
            
            scored_products.append((product, score))
        
        sorted_products = sorted(scored_products, key=lambda x: x[1], reverse=True)
        popular_products = sorted_products[:min(n, len(sorted_products))]
        
        recommendations = []
        for product, score in popular_products:
            price = safe_extract_price(product)
            
            recommendations.append({
                "id": str(product.get("id", "")),
                "title": product.get("title", "") or "Producto",
                "description": safe_clean_text(product.get("body_html"), "body_html"),
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
        """
        if not products:
            logger.warning("No hay productos disponibles para recomendaciones diversas")
            return []
        
        if exclude_products is None:
            exclude_products = set()
            
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
        ]
        
        if not available_products:
            logger.warning("No hay productos disponibles después de excluir las interacciones del usuario")
            if len(products) > 0:
                non_excluded = [p for p in products if str(p.get("id", "")) not in exclude_products]
                if non_excluded:
                    available_products = non_excluded
                else:
                    available_products = random.sample(products, min(n, len(products)))
                logger.info(f"Utilizando {len(available_products)} productos como fallback")
            else:
                logger.error("No hay productos disponibles en absoluto")
                return []
        
        products_by_category = {}
        for product in available_products:
            category = product.get("product_type", "General")
            if category not in products_by_category:
                products_by_category[category] = []
            products_by_category[category].append(product)
        
        diverse_products = []
        categories = list(products_by_category.keys())
        
        num_categories = min(n, len(categories))
        
        if num_categories == 0:
            logger.warning("No hay categorías disponibles para recomendaciones diversas")
            return await ImprovedFallbackStrategies.get_popular_products(
                products, 
                n,
                exclude_products
            )
            
        products_per_category = max(1, n // num_categories)
        selected_categories = random.sample(categories, num_categories)
        
        for category in selected_categories:
            category_products = products_by_category[category]
            num_to_take = min(products_per_category, len(category_products))
            if num_to_take > 0:
                selected_products = random.sample(category_products, num_to_take)
                diverse_products.extend(selected_products)
        
        if len(diverse_products) < n:
            remaining_products = []
            for category in categories:
                if category not in selected_categories:
                    remaining_products.extend(products_by_category[category])
            
            num_additional = min(n - len(diverse_products), len(remaining_products))
            if num_additional > 0:
                additional_products = random.sample(remaining_products, num_additional)
                diverse_products.extend(additional_products)
        
        if len(diverse_products) < n:
            logger.info("No hay suficientes productos diversos, complementando con populares")
            additional_needed = n - len(diverse_products)
            
            additional_exclude = exclude_products.union({
                str(p.get("id", "")) for p in diverse_products
            })
            
            popular_products = await ImprovedFallbackStrategies.get_popular_products(
                products,
                additional_needed,
                additional_exclude
            )
            
            diverse_products.extend(popular_products)
        
        diverse_products = diverse_products[:n]
        
        recommendations = []
        for product in diverse_products:
            price = safe_extract_price(product)
            
            recommendations.append({
                "id": str(product.get("id", "")),
                "title": product.get("title", "") or "Producto",
                "description": safe_clean_text(product.get("body_html"), "body_html"),
                "price": price,
                "category": product.get("product_type", ""),
                "score": 0.5,
                "recommendation_type": "diverse_fallback"
            })
        
        logger.info(f"Generadas {len(recommendations)} recomendaciones diversas (excluyendo productos vistos)")
        return recommendations
    
    @staticmethod
    async def get_personalized_fallback(
        user_id: str,
        products: List[Dict],
        user_events: Optional[List[Dict]] = None,
        n: int = 5,
        user_query: Optional[str] = None  # ✨ NUEVO PARÁMETRO
    ) -> List[Dict]:
        """
        Genera recomendaciones personalizadas fallback basándose en eventos previos
        del usuario si están disponibles, o en heurísticas si no hay datos previos.
        
        ✨ MEJORA: Ahora detecta categoría desde la query del usuario y la prioriza
        sobre las categorías preferidas históricas.
        
        Args:
            user_id: ID del usuario
            products: Lista de productos disponibles
            user_events: Lista de eventos previos del usuario (opcional)
            n: Número de recomendaciones a devolver
            user_query: Query del usuario en lenguaje natural (opcional) ✨ NUEVO
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        if not products:
            logger.warning(f"No hay productos disponibles para recomendaciones personalizadas para {user_id}")
            return []
        
        # Obtener productos con los que el usuario ha interactuado
        interacted_products = await ImprovedFallbackStrategies.get_user_interactions(user_id, user_events)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # ✨ NUEVA LÓGICA: Detectar categoría desde query del usuario
        # ═══════════════════════════════════════════════════════════════════════════
        query_category = None
        if user_query:
            # Obtener categorías disponibles en el catálogo
            available_categories = set(p.get("product_type", "") for p in products if p.get("product_type"))
            
            # Intentar detectar categoría en la query
            query_category = extract_category_from_query(user_query, available_categories)
            
            if query_category:
                logger.info(f"🎯 QUERY-DRIVEN: Detected category '{query_category}' from user query, prioritizing over historical preferences")
                
                # Buscar productos de la categoría detectada
                category_products = [
                    p for p in products 
                    if p.get("product_type", "") == query_category
                    and str(p.get("id", "")) not in interacted_products
                ]
                
                if category_products:
                    logger.info(f"✅ Found {len(category_products)} products in category '{query_category}'")
                    
                    # Tomar productos aleatorios de esta categoría
                    num_to_take = min(n, len(category_products))
                    selected_products = random.sample(category_products, num_to_take)
                    
                    # Si necesitamos más productos, complementar con populares de la misma categoría
                    if len(selected_products) < n:
                        remaining_needed = n - len(selected_products)
                        additional_exclude = interacted_products.union({
                            str(p.get("id", "")) for p in selected_products
                        })
                        
                        # Intentar obtener más de la misma categoría
                        additional_category = [
                            p for p in category_products
                            if str(p.get("id", "")) not in additional_exclude
                        ]
                        
                        if additional_category and remaining_needed <= len(additional_category):
                            additional = random.sample(additional_category, remaining_needed)
                            selected_products.extend(additional)
                        else:
                            # Si no hay suficientes en la categoría, usar populares generales
                            logger.info(f"⚠️ Not enough products in '{query_category}', using general popular products")
                            popular = await ImprovedFallbackStrategies.get_popular_products(
                                products,
                                remaining_needed,
                                additional_exclude
                            )
                            # Convertir popular products de dict a product objects
                            for pop_rec in popular:
                                for p in products:
                                    if str(p.get("id", "")) == pop_rec["id"]:
                                        selected_products.append(p)
                                        break
                    
                    # Convertir a formato de respuesta
                    recommendations = []
                    for i, product in enumerate(selected_products):
                        price = safe_extract_price(product)
                        score = 0.95 - (i * 0.05)  # Alto score porque es query-driven
                        score = max(0.7, score)
                        
                        recommendations.append({
                            "id": str(product.get("id", "")),
                            "title": product.get("title", "") or "Producto",
                            "description": safe_clean_text(product.get("body_html"), "body_html"),
                            "price": price,
                            "category": product.get("product_type", ""),
                            "score": score,
                            "recommendation_type": "query_category_driven"  # ✨ Nuevo tipo
                        })
                    
                    logger.info(f"✅ Generated {len(recommendations)} query-driven recommendations for category '{query_category}'")
                    return recommendations
                else:
                    logger.warning(f"⚠️ Category '{query_category}' detected but no products available, falling back to historical preferences")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # LÓGICA ORIGINAL: Si no hay query category, usar categorías preferidas históricas
        # ═══════════════════════════════════════════════════════════════════════════
        
        # Si tenemos eventos previos del usuario
        if user_events and len(user_events) > 0:
            logger.info(f"Generando recomendaciones personalizadas para {user_id} basadas en {len(user_events)} eventos")
            
            # Extraer categorías preferidas del usuario
            preferred_categories = []
            product_views = Counter()
            
            for event in user_events:
                product_id = event.get("productId") or event.get("product_id")
                if product_id:
                    product_views[product_id] += 1
                    
                    for product in products:
                        if str(product.get("id", "")) == product_id:
                            category = product.get("product_type", "General")
                            preferred_categories.append(category)
                            break
            
            category_counts = Counter(preferred_categories)
            top_categories = [category for category, _ in category_counts.most_common(3)]
            
            if top_categories:
                logger.info(f"Categorías preferidas para usuario {user_id}: {top_categories}")
                
                preferred_products = []
                
                for category in top_categories:
                    category_products = [
                        p for p in products 
                        if p.get("product_type", "General") == category
                        and str(p.get("id", "")) not in interacted_products
                    ]
                    
                    if category_products:
                        products_per_category = max(1, n // len(top_categories))
                        num_to_take = min(products_per_category, len(category_products))
                        selected = random.sample(category_products, num_to_take)
                        preferred_products.extend(selected)
                
                if len(preferred_products) < n:
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
                
                personalized_products = preferred_products[:n]
                
                if len(personalized_products) < n:
                    logger.info(f"No hay suficientes productos en las categorías preferidas, usando populares")
                    return await ImprovedFallbackStrategies.get_popular_products(
                        products, 
                        n,
                        exclude_products=interacted_products
                    )
            else:
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
            price = safe_extract_price(product)
            score = 0.9 - (i * 0.05)
            score = max(0.5, score)
            
            recommendations.append({
                "id": str(product.get("id", "")),
                "title": product.get("title", "") or "Producto",
                "description": safe_clean_text(product.get("body_html"), "body_html"),
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
        n: int = 5,
        exclude_products: Optional[Set[str]] = None,
        user_query: Optional[str] = None  # ✨ NUEVO PARÁMETRO
    ) -> List[Dict]:
        """
        Estrategia de fallback inteligente que selecciona la mejor
        estrategia basada en el contexto y excluye productos ya vistos.
        
        ✨ MEJORA: Ahora acepta user_query para detección de categoría.
        
        Args:
            user_id: ID del usuario
            products: Lista de productos disponibles
            user_events: Lista de eventos previos del usuario (opcional)
            n: Número de recomendaciones a devolver
            exclude_products: Set de IDs de productos a excluir (opcional)
            user_query: Query del usuario en lenguaje natural (opcional) ✨ NUEVO
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        interacted_products = await ImprovedFallbackStrategies.get_user_interactions(user_id, user_events)
        
        combined_exclude = set()
        if interacted_products:
            combined_exclude.update(interacted_products)
        if exclude_products:
            combined_exclude.update(exclude_products)
            
        logger.info(f"Smart fallback exclusions: {len(interacted_products)} from interactions + {len(exclude_products or set())} from context = {len(combined_exclude)} total")
        
        # ✨ PRIORIZAR: Si hay query con categoría, usar personalized_fallback que ahora la detecta
        if user_query:
            logger.info(f"🎯 Using query-aware personalized fallback with query: '{user_query[:50]}...'")
            return await ImprovedFallbackStrategies.get_personalized_fallback(
                user_id, 
                products, 
                user_events, 
                n,
                user_query=user_query  # ✨ Pasar query
            )
        
        # Si tenemos eventos del usuario pero no query, usar recomendaciones personalizadas
        if user_events and len(user_events) > 0:
            logger.info(f"Usando fallback personalizado para usuario {user_id} con {len(user_events)} eventos")
            return await ImprovedFallbackStrategies.get_personalized_fallback(
                user_id, products, user_events, n
            )
        
        # Si es un usuario nuevo, alternar entre productos populares y diversos
        random_choice = random.random()
        if random_choice < 0.7:
            logger.info(f"Usando fallback popular para usuario {user_id}")
            return await ImprovedFallbackStrategies.get_popular_products(
                products, 
                n, 
                exclude_products=combined_exclude
            )
        else:
            logger.info(f"Usando fallback diverso para usuario {user_id}")
            return await ImprovedFallbackStrategies.get_diverse_category_products(
                products, 
                n, 
                exclude_products=combined_exclude
            )