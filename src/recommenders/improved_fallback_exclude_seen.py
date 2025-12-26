"""
Estrategias mejoradas de fallback para el sistema de recomendaciones.

Esta versión incluye la capacidad de excluir productos que el usuario
ya ha visto o añadido al carrito, Y DETECCIÓN DE CATEGORÍA DESDE LA QUERY DEL USUARIO.

✨ MEJORA FASE 3B: Query-aware category detection
"""
# ═══════════════════════════════════════════════════════════════════════════
# ✨ NUEVA ARQUITECTURA: Mapeo Jerárquico de Categorías
# ═══════════════════════════════════════════════════════════════════════════

"""
Estructura del Mapeo:

type: "parent" | "concrete"
  - parent: Categoría virtual que agrupa subcategorías (no existe en catálogo)
  - concrete: Categoría real que existe en el catálogo de productos

subcategories: List[str] (solo para type="parent")
  - Lista de categorías hijas que se deben incluir cuando se detecta el keyword padre

keywords: List[str]
  - Palabras clave que activan esta categoría
  - Incluye singular, plural, variantes ortográficas, sinónimos
  - Normalización automática (lowercase, sin acentos, stem)

Ejemplo de Uso:
  Query: "vestidos elegantes"
  → Detecta keyword "vestido" en VESTIDOS (parent)
  → Expande a: ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS"]
  → Devuelve mix de productos de las 3 categorías
"""


import logging
from typing import List, Dict, Optional, Set
import random
from collections import Counter
import re

logger = logging.getLogger(__name__)


CATEGORY_KEYWORDS = {
    # ═══════════════════════════════════════════════════════════════════════════
    # CATEGORÍAS PADRE (VIRTUALES) - Agrupan múltiples categorías específicas
    # ═══════════════════════════════════════════════════════════════════════════
    
    "VESTIDOS": {
        "type": "parent",
        "subcategories": ["VESTIDOS LARGOS", "VESTIDOS CORTOS", "VESTIDOS MIDIS"],
        "keywords": [
            # Genéricos (español)
            "vestido", "vestidos",
            # Genéricos (inglés)
            "dress", "dresses",
            # Contextuales
            "vestido fiesta", "party dress",
            "vestido evento", "event dress",
        ]
    },
    
    "ENTERITOS": {
        "type": "parent",
        "subcategories": ["ENTERITOS LARGOS", "ENTERITOS CORTOS"],
        "keywords": [
            # Genéricos
            "enterito", "enteritos",
            "enterizo", "enterizos",  # Variante ortográfica
            # Inglés
            "jumpsuit", "jumpsuits",
            "overall", "overalls",
        ]
    },
    
    "CAPAS": {
        "type": "parent",
        "subcategories": ["CAPAS BORDADAS", "CAPAS GASA"],
        "keywords": [
            "capa", "capas",
            "cape", "capes",
            "poncho", "ponchos",  # Similar style
        ]
    },
    
    "VESTIDOS_NOVIA": {
        "type": "parent",
        "subcategories": ["NOVIAS LARGOS", "NOVIAS CORTOS", "NOVIAS MIDIS"],
        "keywords": [
            # Contexto boda
            "vestido novia", "vestido de novia",
            "traje novia",
            "wedding dress",
            "bride dress", "bridal dress",
            # Keywords relacionados
            "boda", "wedding",
            "novia", "bride",
        ]
    },
    
    "CONJUNTOS": {
        "type": "parent",
        "subcategories": [
            "CONJUNTOS FALDAS", 
            "CONJUNTOS PANTALONES",
            "NOVIAS CONJUNTOS FALDAS",
            "NOVIAS CONJUNTOS PANTALONES"
        ],
        "keywords": [
            "conjunto", "conjuntos",
            "set", "sets",
            "outfit", "outfits",
            "two piece", "2 piece",
        ]
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CATEGORÍAS CONCRETAS - Existen en el catálogo de productos
    # ═══════════════════════════════════════════════════════════════════════════
    
    "ZAPATOS": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "zapato", "zapatos",
            "shoe", "shoes",
            "calzado", "footwear",
            # Tipos específicos
            "sandalia", "sandalias", "sandal", "sandals",
            "bota", "botas", "boot", "boots",
            "tenis", "sneaker", "sneakers",
            # Heels
            "taco", "tacos",
            "heel", "heels",
            "stiletto", "stilettos",
            # Regionales
            "chancla", "chanclas",  # MX, CO: flip-flops
            "alpargata", "alpargatas",  # ES: espadrilles
        ]
    },
    
    "VESTIDOS LARGOS": {
        "type": "concrete",
        "keywords": [
            # Específicos
            "vestido largo", "vestidos largos",
            "long dress",
            "maxi dress",
            # Ocasiones
            "vestido de noche", "evening dress",
            "vestido gala", "gala dress",
            "vestido fiesta largo", "long party dress",
        ]
    },
    
    "VESTIDOS CORTOS": {
        "type": "concrete",
        "keywords": [
            # Específicos
            "vestido corto", "vestidos cortos",
            "short dress",
            "mini dress",
            # Ocasiones
            "vestido casual",
            "vestido coctel", "cocktail dress",
            "vestido dia", "day dress",
        ]
    },
    
    "VESTIDOS MIDIS": {
        "type": "concrete",
        "keywords": [
            # Específicos
            "vestido midi", "vestidos midis",
            "midi dress",
            "vestido medio", "medium dress",
            # Descripción
            "vestido rodilla", "knee length dress",
        ]
    },
    
    "PANTALONES": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "pantalon", "pantalones",
            "pants", "trousers",
            # Tipos
            "jean", "jeans",
            "vaquero", "vaqueros",
            # Regionales
            "mezclilla",  # MX: denim
            "mahon", "mahones",  # PR: jeans
            # Estilos
            "leggins", "leggings",
        ]
    },
    
    "FALDAS": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "falda", "faldas",
            "skirt", "skirts",
            # Regionales
            "enagua", "enaguas",  # Regional: petticoat/skirt
            "pollera", "polleras",  # AR, UY: skirt
        ]
    },
    
    "TOPS": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "top", "tops",
            "blusa", "blusas", "blouse",
            "camisa", "camisas", "shirt",
            # Regionales
            "playera", "playeras",  # MX: t-shirt
            "franela", "franelas",  # VE: t-shirt
            "polera", "poleras",  # CL: t-shirt
            # Tipos
            "camiseta", "camisetas", "t-shirt",
        ]
    },
    
    "BRALETTES": {
        "type": "concrete",
        "keywords": [
            # Producto específico
            "bralette", "bralettes",
            # Genéricos
            "sosten", "sostén", "sostenes",
            "sujetador", "sujetadores",
            "bra", "bras",
            # Regionales
            "brasier", "brasieres",  # MX
            "corpiño", "corpiños",  # AR
        ]
    },
    
    "LENCERIA": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "lenceria", "lencería",
            "lingerie",
            "ropa interior", "underwear",
            # Descriptivos
            "intima", "intimas", "intimate",
            "sensual", "sexy",
        ]
    },
    
    "ACCESSORIES": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "accesorio", "accesorios",
            "accessory", "accessories",
            "complemento", "complementos",
            # Descriptivos
            "detalle", "detalles",
        ]
    },
    
    "CLUTCH": {
        "type": "concrete",
        "keywords": [
            # Producto específico
            "clutch", "clutches",
            # Genéricos
            "bolso", "bolsos", "bag", "bags",
            "cartera", "carteras", "purse",
            # Regionales
            "bolsa", "bolsas",  # MX: bag
            "morral", "morrales",  # CO: backpack/bag
            "bandolera", "bandoleras",  # Crossbody bag
        ]
    },
    
    "BRAZALETES": {
        "type": "concrete",
        "keywords": [
            # Producto específico
            "brazalete", "brazaletes",
            # Genéricos
            "pulsera", "pulseras",
            "bracelet", "bracelets",
            # Regionales
            "manilla", "manillas",  # CO: bracelet
            "tobillera", "tobilleras",  # Anklet
        ]
    },
    
    "COLLARES": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "collar", "collares",
            "necklace", "necklaces",
            # Tipos
            "cadena", "cadenas", "chain",
            "gargantilla", "gargantillas", "choker",
            "colgante", "colgantes", "pendant",
        ]
    },
    
    "AROS": {
        "type": "concrete",
        "keywords": [
            # Producto específico
            "aro", "aros",
            # Variantes principales
            "arete", "aretes",  # MX, común
            "pendiente", "pendientes",
            # Inglés
            "earring", "earrings",
            # Regionales
            "zarcillo", "zarcillos",  # VE, CO
            "caravana", "caravanas",  # AR
            "chapita", "chapitas",  # Stud earrings
        ]
    },
    
    "CINTURONES": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "cinturon", "cinturones", "cinturón",
            "belt", "belts",
            # Variantes
            "correa", "correas",
            "cinto", "cintos",  # BR, PT
            # Estilo
            "faja", "fajas",  # Belt-style
        ]
    },
    
    "CHAQUETAS": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "chaqueta", "chaquetas",
            "jacket", "jackets",
            "abrigo", "abrigos", "coat",
            # Regionales
            "chamarra", "chamarras",  # MX
            "campera", "camperas",  # AR
            "saco", "sacos",  # Formal jacket
            # Tipos
            "blazer", "blazers",
            "cardigan", "cardigans",
        ]
    },
    
    "KIMONOS": {
        "type": "concrete",
        "keywords": [
            # Producto específico
            "kimono", "kimonos",
            # Similar styles
            "cardigan", "cardigans",
            "bata", "batas",  # Robe
            "oversize cardigan",
        ]
    },
    
    "CAPAS BORDADAS": {
        "type": "concrete",
        "keywords": [
            # Específico
            "capa bordada", "capas bordadas",
            "embroidered cape",
            # Descriptivos
            "capa decorada", "decorated cape",
        ]
    },
    
    "CAPAS GASA": {
        "type": "concrete",
        "keywords": [
            # Específico
            "capa gasa", "capas gasa",
            "chiffon cape",
            # Material
            "capa ligera", "light cape",
        ]
    },
    
    "ENTERITOS LARGOS": {
        "type": "concrete",
        "keywords": [
            # Específico
            "enterito largo", "enteritos largos",
            "enterizo largo", "enterizos largos",
            # Inglés
            "long jumpsuit",
            "maxi jumpsuit",
            # Descriptivos
            "overall largo", "long overall",
        ]
    },
    
    "ENTERITOS CORTOS": {
        "type": "concrete",
        "keywords": [
            # Específico
            "enterito corto", "enteritos cortos",
            "enterizo corto", "enterizos cortos",
            # Inglés
            "short jumpsuit",
            "romper", "rompers",
            "playsuit", "playsuits",
        ]
    },
    
    "PIJAMAS": {
        "type": "concrete",
        "keywords": [
            # Genéricos
            "pijama", "pijamas",
            "pajamas",
            "sleepwear",
            # Variantes
            "piyama", "piyamas",
            # Descriptivos
            "ropa dormir", "ropa de dormir",
            "nightwear",
            "pjs",
        ]
    },
    
    "NOVIAS LARGOS": {
        "type": "concrete",
        "keywords": [
            # Específico
            "vestido novia largo",
            "vestido de novia largo",
            # Inglés
            "long wedding dress",
            "long bride dress",
            "long bridal dress",
            # Contexto
            "traje novia largo",
        ]
    },
    
    "NOVIAS CORTOS": {
        "type": "concrete",
        "keywords": [
            # Específico
            "vestido novia corto",
            "vestido de novia corto",
            # Inglés
            "short wedding dress",
            "short bride dress",
            "short bridal dress",
        ]
    },
    
    "NOVIAS MIDIS": {
        "type": "concrete",
        "keywords": [
            # Específico
            "vestido novia midi",
            "vestido de novia midi",
            # Inglés
            "midi wedding dress",
            "midi bride dress",
            "midi bridal dress",
        ]
    },
    
    # Agregar más categorías según el catálogo...
    "CONJUNTOS FALDAS": {
        "type": "concrete",
        "keywords": [
            "conjunto falda",
            "set skirt",
            "two piece skirt",
        ]
    },
    
    "CONJUNTOS PANTALONES": {
        "type": "concrete",
        "keywords": [
            "conjunto pantalon",
            "set pants",
            "two piece pants",
        ]
    },
    
    "LEGGINGS": {
        "type": "concrete",
        "keywords": [
            "leggins", "leggings",
            "malla", "mallas",
            "tight", "tights",
        ]
    },
    
    "REDUCTORES": {
        "type": "concrete",
        "keywords": [
            "reductor", "reductores",
            "faja", "fajas",
            "shapewear",
            "moldeador", "moldeadores",
        ]
    },
    
    "CALZONES": {
        "type": "concrete",
        "keywords": [
            "calzon", "calzones",
            "panty", "panties",
            "bragas",
            "ropa interior mujer",
        ]
    },
    
    "TOCADOS": {
        "type": "concrete",
        "keywords": [
            "tocado", "tocados",
            "headpiece", "headpieces",
            "diadema", "diademas",
            "corona", "coronas",
        ]
    },
    
    "CARTERAS": {
        "type": "concrete",
        "keywords": [
            "cartera", "carteras",
            "handbag", "handbags",
            "bolso mano",
        ]
    },
    
    "AROMAS": {
        "type": "concrete",
        "keywords": [
            "aroma", "aromas",
            "perfume", "perfumes",
            "fragancia", "fragancias",
            "esencia", "esencias",
        ]
    },
    
    "ALAS DE NOVIA": {
        "type": "concrete",
        "keywords": [
            "ala novia", "alas novia",
            "velo", "velos",
            "veil", "veils",
        ]
    },
    
    "GIFTCARD": {
        "type": "concrete",
        "keywords": [
            "giftcard", "gift card",
            "tarjeta regalo",
            "vale", "vales",
            "cupon", "cupón",
        ]
    },
    
    "PACK": {
        "type": "concrete",
        "keywords": [
            "pack", "packs",
            "paquete", "paquetes",
            "combo", "combos",
            "bundle", "bundles",
        ]
    },
    
    "SNOWBOARD": {
        "type": "concrete",
        "keywords": [
            "snowboard", "snowboards",
            "tabla nieve",
            "snow board",
        ]
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# NUEVA FUNCIÓN: Detección de Múltiples Categorías
# ═══════════════════════════════════════════════════════════════════════════

def extract_categories_from_query(
    query: str, 
    available_categories: Set[str]
) -> List[str]:
    """
    Detecta todas las categorías mencionadas en la query del usuario.
    
    Proceso:
    1. Normalizar query (lowercase, sin acentos)
    2. Para cada categoría en CATEGORY_KEYWORDS:
       a. Buscar si algún keyword aparece en la query
       b. Si es categoría padre → expandir a subcategorías
       c. Si es categoría concreta → agregar directamente
    3. Eliminar duplicados
    4. Filtrar solo categorías que existen en available_categories
    
    Args:
        query: Query del usuario en lenguaje natural
        available_categories: Set de categorías concretas en el catálogo
        
    Returns:
        List[str]: Lista de categorías concretas detectadas (ordenadas por especificidad)
    """
    if not query:
        return []
    
    # 1. Normalizar query
    query_lower = query.lower()
    query_normalized = query_lower.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    
    # 2. Trackear categorías detectadas y su especificidad
    detected_categories = {}  # {category: specificity_score}
    
    # 3. Iterar sobre todas las categorías y sus keywords
    for category, config in CATEGORY_KEYWORDS.items():
        keywords = config.get("keywords", [])
        category_type = config.get("type")
        
        # Buscar cada keyword en la query
        for keyword in keywords:
            keyword_normalized = keyword.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
            
            # Buscar con word boundaries para evitar false positives
            pattern = r'\b' + re.escape(keyword_normalized) + r'\b'
            
            if re.search(pattern, query_normalized):
                # Calcular especificidad (keywords más largos = más específicos)
                specificity = len(keyword.split())  # Número de palabras
                
                # Si es categoría padre → expandir a subcategorías
                if category_type == "parent":
                    subcategories = config.get("subcategories", [])
                    for subcat in subcategories:
                        # Solo agregar si existe en el catálogo
                        if subcat in available_categories:
                            # Dar menor prioridad a expansiones (0.5 * especificidad)
                            current_specificity = detected_categories.get(subcat, 0)
                            detected_categories[subcat] = max(current_specificity, specificity * 0.5)
                            
                    logger.debug(f"🎯 Expanded parent '{category}' (keyword: '{keyword}') → {subcategories}")
                
                # Si es categoría concreta
                elif category_type == "concrete":
                    # Solo agregar si existe en el catálogo
                    if category in available_categories:
                        current_specificity = detected_categories.get(category, 0)
                        detected_categories[category] = max(current_specificity, specificity)
                        
                        logger.debug(f"🎯 Detected concrete '{category}' (keyword: '{keyword}', specificity: {specificity})")
    
    # 4. Si no se detectó nada, retornar lista vacía
    if not detected_categories:
        logger.debug(f"🔍 No category detected in query: '{query[:50]}...'")
        return []
    
    # 5. Ordenar por especificidad (más específico primero)
    # Esto asegura que "vestido largo" tenga prioridad sobre expansión de "vestido"
    sorted_categories = sorted(
        detected_categories.items(),
        key=lambda x: x[1],  # Ordenar por specificity
        reverse=True
    )
    
    # 6. Extraer solo los nombres de categorías
    result = [cat for cat, _ in sorted_categories]
    
    # 7. Log resultado
    if len(result) == 1:
        logger.info(f"🎯 Single category detected from query: '{result[0]}'")
    else:
        logger.info(f"🎯 Multiple categories detected from query: {result}")
        logger.info(f"   Query: '{query[:50]}...'")
    
    return result

# ═══════════════════════════════════════════════════════════════════════════
# ACTUALIZACIÓN: Mantener función original para backward compatibility
# ═══════════════════════════════════════════════════════════════════════════

# def extract_category_from_query(query: str, available_categories: Set[str]) -> Optional[str]:
#     """
#     Extrae la categoría mencionada en la query del usuario.
    
#     Usa un mapeo de palabras clave para detectar categorías específicas,
#     priorizando coincidencias exactas de múltiples palabras sobre palabras individuales.
    
#     Args:
#         query: Query del usuario en lenguaje natural
#         available_categories: Set de categorías disponibles en el catálogo
        
#     Returns:
#         str: Nombre de la categoría detectada o None si no se detecta ninguna
        
#     Examples:
#         >>> extract_category_from_query("necesito zapatos formales", {"ZAPATOS", "VESTIDOS"})
#         'ZAPATOS'
        
#         >>> extract_category_from_query("vestido largo para boda", {"VESTIDOS LARGOS"})
#         'VESTIDOS LARGOS'
        
#         >>> extract_category_from_query("algo elegante", {"ZAPATOS", "VESTIDOS"})
#         None
#     """
#     if not query:
#         return None
    
#     # Normalizar query: lowercase y remover acentos básicos
#     query_lower = query.lower()
#     query_normalized = query_lower.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    
#     # Trackear coincidencias con su longitud (para priorizar frases largas)
#     matches = []
    
#     # Iterar sobre cada categoría en el mapeo
#     for category, keywords in CATEGORY_KEYWORDS.items():
#         # Solo considerar categorías que existen en el catálogo
#         if category not in available_categories:
#             continue
            
#         # Buscar cada keyword en la query
#         for keyword in keywords:
#             keyword_normalized = keyword.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
            
#             # Buscar coincidencia de palabra completa (no substring)
#             # Ejemplo: "zapato" no debe matchear "zapatería"
#             pattern = r'\b' + re.escape(keyword_normalized) + r'\b'
#             if re.search(pattern, query_normalized):
#                 # Agregar match con longitud del keyword (más largo = más específico)
#                 matches.append((category, len(keyword)))
#                 logger.debug(f"🔍 Query keyword match: '{keyword}' → {category}")
    
#     if not matches:
#         logger.debug(f"🔍 No category detected in query: '{query}'")
#         return None
    
#     # Priorizar coincidencia más larga (más específica)
#     # Ejemplo: "vestido largo" (2 palabras) > "vestido" (1 palabra)
#     best_match = max(matches, key=lambda x: x[1])
#     detected_category = best_match[0]
    
#     logger.info(f"🎯 Category detected from query: '{detected_category}' (from query: '{query[:50]}...')")
#     return detected_category

# ═══════════════════════════════════════════════════════════════════════════
# HELPER: Obtener todas las categorías concretas del catálogo
# ═══════════════════════════════════════════════════════════════════════════

def get_concrete_categories() -> Set[str]:
    """
    Devuelve solo las categorías concretas (que existen en el catálogo).
    Excluye categorías padre (virtuales).
    
    Returns:
        Set[str]: Conjunto de nombres de categorías concretas
    """
    concrete = set()
    for category, config in CATEGORY_KEYWORDS.items():
        if config.get("type") == "concrete":
            concrete.add(category)
    return concrete


def get_parent_categories() -> Dict[str, List[str]]:
    """
    Devuelve mapeo de categorías padre → subcategorías.
    
    Returns:
        Dict[str, List[str]]: {categoria_padre: [sub1, sub2, ...]}
    """
    parents = {}
    for category, config in CATEGORY_KEYWORDS.items():
        if config.get("type") == "parent":
            parents[category] = config.get("subcategories", [])
    return parents

# ═══════════════════════════════════════════════════════════════════════════
# NUEVA FUNCIÓN: Sampling Inteligente entre Múltiples Categorías
# ═══════════════════════════════════════════════════════════════════════════

def smart_sample_across_categories(
    products: List[Dict],
    categories: List[str],
    n: int = 5,
    exclude_products: Optional[Set[str]] = None
) -> List[Dict]:
    """
    Distribuye n productos entre múltiples categorías de forma inteligente.
    
    Estrategia:
    1. Agrupar productos disponibles por categoría
    2. Calcular distribución óptima (equitativa con mínimo 1 por categoría si posible)
    3. Seleccionar aleatoriamente dentro de cada categoría
    4. Si una categoría no tiene suficientes productos, redistribuir a otras
    
    Args:
        products: Lista completa de productos disponibles
        categories: Lista de categorías concretas a incluir (ordenadas por prioridad)
        n: Número total de productos a devolver
        exclude_products: Set de IDs de productos a excluir
        
    Returns:
        List[Dict]: Lista de n productos distribuidos entre categorías
    """
    if not products or not categories or n <= 0:
        return []
    
    if exclude_products is None:
        exclude_products = set()
    
    # 1. Filtrar productos disponibles (excluir vistos)
    available_products = [
        p for p in products 
        if str(p.get("id", "")) not in exclude_products
    ]
    
    if not available_products:
        logger.warning("No products available after exclusions")
        return []
    
    # 2. Agrupar productos por categoría
    products_by_category = {}
    for category in categories:
        category_products = [
            p for p in available_products
            if p.get("product_type", "") == category
        ]
        if category_products:
            products_by_category[category] = category_products
    
    if not products_by_category:
        logger.warning(f"No products found in categories: {categories}")
        return []
    
    # 3. Calcular distribución inicial (equitativa)
    num_categories = len(products_by_category)
    base_per_category = max(1, n // num_categories)
    remainder = n % num_categories
    
    # 4. Asignar productos por categoría
    distribution = {}
    for i, category in enumerate(products_by_category.keys()):
        # Primeras categorías reciben el remainder
        allocation = base_per_category + (1 if i < remainder else 0)
        available_count = len(products_by_category[category])
        
        # Ajustar si la categoría no tiene suficientes productos
        actual_allocation = min(allocation, available_count)
        distribution[category] = actual_allocation
    
    logger.info(f"📊 Distribution plan: {distribution}")
    
    # 5. Seleccionar productos aleatoriamente de cada categoría
    selected_products = []
    for category, count in distribution.items():
        category_products = products_by_category[category]
        
        # Sample aleatorio
        if count <= len(category_products):
            sampled = random.sample(category_products, count)
        else:
            # Si pedimos más de los disponibles, tomar todos
            sampled = category_products
        
        selected_products.extend(sampled)
        logger.debug(f"  ✅ {category}: {len(sampled)} products selected")
    
    # 6. Si no alcanzamos n productos, rellenar con productos de cualquier categoría
    if len(selected_products) < n:
        remaining_needed = n - len(selected_products)
        selected_ids = set(str(p.get("id", "")) for p in selected_products)
        
        # Productos restantes no seleccionados
        remaining_products = [
            p for p in available_products
            if str(p.get("id", "")) not in selected_ids
        ]
        
        if remaining_products:
            additional = random.sample(
                remaining_products,
                min(remaining_needed, len(remaining_products))
            )
            selected_products.extend(additional)
            logger.info(f"🔄 Added {len(additional)} additional products to reach n={n}")
    
    # 7. Limitar a exactamente n productos (por si acaso)
    final_products = selected_products[:n]
    
    logger.info(f"✅ Smart sampling completed: {len(final_products)} products across {num_categories} categories")
    
    return final_products

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
        exclude_products: Optional[Set[str]] = None,
        user_query: Optional[str] = None  # ✨ NUEVO: Para smart diversification
    ) -> List[Dict]:
        """
        Obtiene productos de diversas categorías para ofrecer variedad,
        excluyendo productos con los que el usuario ya ha interactuado.
        
        ✨ MEJORA FASE 4: Smart diversification con query awareness
        Si se proporciona user_query, prioriza categorías relacionadas con la query.
        
        Args:
            products: Lista de productos disponibles
            n: Número de productos a devolver
            exclude_products: Set de IDs a excluir
            user_query: Query del usuario para smart diversification (opcional)
            
        Returns:
            List[Dict]: Productos diversos, priorizando categorías relevantes si hay query
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
        
        # Agrupar productos por categoría
        products_by_category = {}
        for product in available_products:
            category = product.get("product_type", "General")
            if category not in products_by_category:
                products_by_category[category] = []
            products_by_category[category].append(product)
        
        categories = list(products_by_category.keys())
        
        if len(categories) == 0:
            logger.warning("No hay categorías disponibles para recomendaciones diversas")
            return await ImprovedFallbackStrategies.get_popular_products(
                products, 
                n,
                exclude_products
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✨ SMART DIVERSIFICATION: Si hay query, priorizar categorías relevantes
        # ═══════════════════════════════════════════════════════════════════════
        
        if user_query:
            logger.info(f"🎨 Smart diversification with query: '{user_query[:50]}...'")
            
            # Intentar detectar categorías de la query
            available_categories = get_concrete_categories()
            detected_categories = extract_categories_from_query(user_query, available_categories)
            
            if detected_categories:
                # Filtrar categorías detectadas que tienen productos disponibles
                priority_categories = [
                    cat for cat in detected_categories 
                    if cat in products_by_category
                ]
                
                if priority_categories:
                    logger.info(f"   🎯 Priority categories for diversification: {priority_categories[:3]}")
                    
                    # Tomar productos de categorías prioritarias primero
                    diverse_products = []
                    products_per_priority = max(1, n // min(3, len(priority_categories)))
                    
                    for category in priority_categories[:3]:  # Top 3 prioritarias
                        category_products = products_by_category[category]
                        num_to_take = min(products_per_priority, len(category_products))
                        if num_to_take > 0:
                            selected = random.sample(category_products, num_to_take)
                            diverse_products.extend(selected)
                    
                    # Si no alcanzamos n, complementar con otras categorías
                    if len(diverse_products) < n:
                        remaining_needed = n - len(diverse_products)
                        remaining_categories = [
                            cat for cat in categories 
                            if cat not in priority_categories
                        ]
                        
                        if remaining_categories:
                            selected_remaining = random.sample(
                                remaining_categories, 
                                min(2, len(remaining_categories))
                            )
                            
                            for category in selected_remaining:
                                category_products = products_by_category[category]
                                num_to_take = min(
                                    remaining_needed // len(selected_remaining), 
                                    len(category_products)
                                )
                                if num_to_take > 0:
                                    selected = random.sample(category_products, num_to_take)
                                    diverse_products.extend(selected)
                    
                    # Limitar a n
                    diverse_products = diverse_products[:n]
                    
                    logger.info(f"   ✅ Smart diversification: {len(diverse_products)} products from priority + diverse categories")
                    
                    # Formatear recomendaciones
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
                            "recommendation_type": "smart_diverse_fallback"
                        })
                    
                    return recommendations
        
        # ═══════════════════════════════════════════════════════════════════════
        # DIVERSIFICACIÓN ESTÁNDAR (sin query o sin categorías detectadas)
        # ═══════════════════════════════════════════════════════════════════════
        
        logger.info(f"🎨 Standard diversification across {len(categories)} categories")
        
        diverse_products = []
        num_categories = min(n, len(categories))
        products_per_category = max(1, n // num_categories)
        selected_categories = random.sample(categories, num_categories)
        
        for category in selected_categories:
            category_products = products_by_category[category]
            num_to_take = min(products_per_category, len(category_products))
            if num_to_take > 0:
                selected_products = random.sample(category_products, num_to_take)
                diverse_products.extend(selected_products)
        
        # Complementar si falta
        if len(diverse_products) < n:
            remaining_products = []
            for category in categories:
                if category not in selected_categories:
                    remaining_products.extend(products_by_category[category])
            
            num_additional = min(n - len(diverse_products), len(remaining_products))
            if num_additional > 0:
                additional_products = random.sample(remaining_products, num_additional)
                diverse_products.extend(additional_products)
        
        # Último recurso: productos populares
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
        
        # Formatear recomendaciones
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
        exclude_products: Optional[Set[str]] = None,
        user_query: Optional[str] = None  # ✨ NUEVO PARÁMETRO
    ) -> List[Dict]:
        """
        Genera recomendaciones personalizadas de fallback con soporte para múltiples categorías.
        
        ✨ MEJORA FASE 3B: Query-aware multi-category detection
        
        Estrategia de priorización:
        1. Query-driven (múltiples categorías) - Si query detecta categorías específicas
        2. Personalized - Si hay historial de interacciones del usuario
        3. Diverse - Si no hay query ni historial
        4. Popular - Última opción (productos más populares globalmente)
        
        Args:
            user_id: ID del usuario
            products: Lista de productos disponibles
            user_events: Eventos del usuario (interacciones previas)
            n: Número de recomendaciones a generar
            exclude_products: Set de IDs de productos a excluir
            user_query: Query del usuario en lenguaje natural (NUEVO)
            
        Returns:
            List[Dict]: Lista de productos recomendados con scores
        """
        if exclude_products is None:
            exclude_products = set()
        
        # Filtrar productos disponibles
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
        ]
        
        if not available_products:
            logger.warning(f"No products available after exclusions for user {user_id}")
            return []
        
        # ═══════════════════════════════════════════════════════════════════════════
        # PRIORIDAD 1: QUERY-DRIVEN RECOMMENDATIONS (MÚLTIPLES CATEGORÍAS)
        # ═══════════════════════════════════════════════════════════════════════════
        
        if user_query:
            logger.info(f"🎯 Attempting query-driven recommendations for: '{user_query[:50]}...'")
            
            # Obtener categorías disponibles en el catálogo
            available_categories = get_concrete_categories()
            
            # Detectar TODAS las categorías mencionadas en la query
            query_categories = extract_categories_from_query(user_query, available_categories)
            
            if query_categories:
                logger.info(f"🎯 MULTI-CATEGORY QUERY-DRIVEN: Detected {len(query_categories)} categories")
                logger.info(f"   Categories: {query_categories}")
                logger.info(f"   Prioritizing query-detected categories over historical preferences")
                
                # Usar sampling inteligente para distribuir entre categorías
                query_driven_products = smart_sample_across_categories(
                    products=available_products,
                    categories=query_categories,
                    n=n,
                    exclude_products=exclude_products
                )
                
                if query_driven_products:
                    # Agregar scores y metadata
                    recommendations = []
                    for i, product in enumerate(query_driven_products):
                        # Score decreciente: más alto para primeros productos
                        # Rango: 0.95 (primero) → 0.70 (último)
                        score = 0.95 - (i * 0.25 / n)
                        
                        recommendations.append({
                            **product,
                            "score": score,
                            "recommendation_type": "query_category_driven_multi",
                            "detected_categories": query_categories,
                            "query_snippet": user_query[:50]
                        })
                    
                    logger.info(f"✅ Generated {len(recommendations)} multi-category query-driven recommendations")
                    logger.info(f"   Distribution across: {query_categories}")
                    return recommendations
                else:
                    logger.warning(f"⚠️ No products found in detected categories: {query_categories}")
                    # Continuar con siguiente estrategia
            else:
                logger.debug(f"🔍 No categories detected in query: '{user_query[:50]}...'")
                # Continuar con siguiente estrategia
        
        # ═══════════════════════════════════════════════════════════════════════════
        # PRIORIDAD 2: PERSONALIZED RECOMMENDATIONS (HISTORIAL)
        # ═══════════════════════════════════════════════════════════════════════════
        
        if user_events and len(user_events) > 0:
            logger.info(f"📊 Using personalized fallback for user {user_id} with {len(user_events)} events")
            
            # Analizar categorías preferidas del usuario
            user_categories = [
                event.get("product_info", {}).get("product_type", "")
                for event in user_events
                if event.get("product_info", {}).get("product_type")
            ]
            
            if user_categories:
                # Contar frecuencia de cada categoría
                category_counts = {}
                for cat in user_categories:
                    category_counts[cat] = category_counts.get(cat, 0) + 1
                
                # Ordenar por frecuencia (más interactuadas primero)
                sorted_categories = sorted(
                    category_counts.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                
                # Tomar top 3 categorías preferidas
                preferred_categories = [cat for cat, count in sorted_categories[:3]]
                
                logger.info(f"   Preferred categories: {preferred_categories}")
                
                # Generar recomendaciones de categorías preferidas
                personalized_products = []
                
                for category in preferred_categories:
                    category_products = [
                        p for p in available_products
                        if p.get("product_type") == category
                    ]
                    
                    if category_products:
                        # Sample aleatorio de esta categoría
                        sample_size = min(3, len(category_products))
                        sampled = random.sample(category_products, sample_size)
                        personalized_products.extend(sampled)
                
                # Si tenemos productos personalizados
                if personalized_products:
                    # Limitar a n productos
                    personalized_products = personalized_products[:n]
                    
                    # Agregar scores
                    recommendations = []
                    for i, product in enumerate(personalized_products):
                        # Score decreciente: 0.9 → 0.5
                        score = 0.9 - (i * 0.4 / n)
                        
                        recommendations.append({
                            **product,
                            "score": score,
                            "recommendation_type": "personalized_fallback",
                            "based_on_categories": preferred_categories
                        })
                    
                    logger.info(f"✅ Generated {len(recommendations)} personalized recommendations")
                    return recommendations
        
        # ═══════════════════════════════════════════════════════════════════════════
        # PRIORIDAD 3: DIVERSE CATEGORY RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════════════════════
        
        logger.info(f"🌈 Using diverse category recommendations for user {user_id}")
        
        diverse_products = await ImprovedFallbackStrategies.get_diverse_category_products(
            products=available_products,
            n=n,
            exclude_products=exclude_products,
            user_query=user_query  # Pasar query para smart diversification
        )
        
        if diverse_products:
            # Agregar scores
            recommendations = []
            for i, product in enumerate(diverse_products):
                score = 0.5  # Score fijo para diverse
                
                recommendations.append({
                    **product,
                    "score": score,
                    "recommendation_type": "diverse_fallback"
                })
            
            logger.info(f"✅ Generated {len(recommendations)} diverse recommendations")
            return recommendations
        
        # ═══════════════════════════════════════════════════════════════════════════
        # PRIORIDAD 4: POPULAR PRODUCTS (ÚLTIMO RECURSO)
        # ═══════════════════════════════════════════════════════════════════════════
        
        logger.warning(f"⚠️ Falling back to popular products for user {user_id}")
        
        # Selección aleatoria simple
        if len(available_products) <= n:
            selected = available_products
        else:
            selected = random.sample(available_products, n)
        
        recommendations = []
        for i, product in enumerate(selected):
            recommendations.append({
                **product,
                "score": 0.3,
                "recommendation_type": "popular_fallback"
            })
        
        logger.info(f"✅ Generated {len(recommendations)} popular fallback recommendations")
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