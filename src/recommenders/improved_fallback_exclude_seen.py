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
            # FIX (13/06/2026 — CH-multilang): FR/DE/IT keywords para mercado CH.
            # Sin estas palabras, queries en francés/alemán/italiano no detectan
            # VESTIDOS y el fallback cae a diversificación de 42 categorías
            # incluyendo accesorios baratos. Con estas keywords, el sistema
            # identifica correctamente la categoría de ropa.
            "robe", "robes",                           # FR: vestido
            "robe de soirée", "robe habillée",         # FR: vestido de noche/fiesta
            "robe élégante",                           # FR: vestido elegante
            "kleid", "kleider",                        # DE: vestido
            "abendkleid", "partyKleid",                # DE: vestido de noche/fiesta
            "vestito", "vestiti",                      # IT: vestido
            "abito", "abiti",                          # IT: vestido/traje formal
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
            # FIX (13/06/2026 — CH-multilang): FR/DE/IT boda/casamiento
            "mariage", "mariée", "robe de mariée",     # FR: boda, novia, vestido novia
            "mariage civil", "robe nuptiale",           # FR: variantes
            "hochzeit", "brautkleid", "hochzeitskleid", # DE: boda, vestido novia
            "matrimonio", "sposa", "abito da sposa",    # IT: matrimonio, novia, vestido novia
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
            "two piece", "2 piece",
            # FIX (11/07/2026): se quitaron "outfit"/"outfits" de aqui. Eran
            # demasiado genericos -- "outfit" en espanol/spanglish se usa para
            # referirse al look completo ("completa el outfit"), no especificamente
            # a un conjunto de dos piezas. Efecto real confirmado en logs de
            # produccion (11/07/2026): la query genuinamente generica "completa el
            # outfit" (sobre un producto CARTERAS) matcheaba el keyword "outfit" ->
            # expandia a CONJUNTOS FALDAS/PANTALONES -> F-08B acotaba la busqueda a
            # target_categories=['conjunto'], devolviendo solo 3 productos en vez
            # del fallback amplio esperado (dress/top/accessory/enterito/outerwear).
            # Antes del fix de hoy (ZAPATOS/CONJUNTOS en _B08_SHOPIFY_TO_OUTFIT_CAT)
            # esta deteccion falsa ya ocurria pero se descartaba en silencio (las
            # claves CONJUNTOS FALDAS/PANTALONES no existian en ese diccionario) --
            # dos bugs que se cancelaban. Al completar el mapeo, la deteccion falsa
            # quedo expuesta. "conjunto"/"conjuntos"/"set"/"two piece" siguen
            # detectando CONJUNTOS correctamente sin este keyword generico.
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
            # Español
            "vestido largo", "vestidos largos",
            # Inglés
            "long dress",
            "maxi dress",
            # Ocasiones ES
            "vestido de noche", "evening dress",
            "vestido gala", "gala dress",
            "vestido fiesta largo", "long party dress",
            # FIX (15/06/2026 — CH-multilang): keywords FR/DE/IT para vestidos LARGOS.
            # "robe longue" (2 palabras, specificity=2) permite que Change 1 suprima
            # VESTIDOS CORTOS / VESTIDOS MIDIS cuando el usuario pide vestidos largos.
            "robe longue", "robes longues",         # FR: vestido largo
            "robe maxi",                            # FR: maxi vestido
            # FIX (16/06/2026 — typo tolerance FR): "robes longe" (typo de "longue")
            # no matcheaba ninguno de los keywords anteriores porque falta la 'u'.
            # "robes long" ES SUBSTRING de "robes longe", "robes longues" y "robes longue".
            # Con specificity=2 (2 palabras), Change 1 sigue suprimiendo las hermanas.
            # Cubre: "robes longe" (typo), "robes long" (EN-influenced), "robes longues" (ya OK).
            "robes long",                           # FR prefix: robes lon(gue/ges/ge)
            "langes kleid", "lange kleider",        # DE: vestido largo
            "maxi kleid",                           # DE: maxi vestido
            "vestito lungo", "vestiti lunghi",      # IT: vestido largo
            "abito lungo",                          # IT: vestido largo (formal)
        ]
    },
    
    "VESTIDOS CORTOS": {
        "type": "concrete",
        "keywords": [
            # Español
            "vestido corto", "vestidos cortos",
            # Inglés
            "short dress",
            "mini dress",
            # Ocasiones ES
            "vestido casual",
            "vestido coctel", "cocktail dress",
            "vestido dia", "day dress",
            # FIX (15/06/2026 — CH-multilang): keywords FR/DE/IT para vestidos CORTOS.
            # Sin estas palabras, "Montrez-moi des robes courtes" expande el padre VESTIDOS
            # a los 3 hijos (3:3:2) en lugar de mostrar solo VESTIDOS CORTOS.
            # Con un keyword de 2+ palabras (specificity=2 > 0.5), Change 1 suprime
            # las hermanas VESTIDOS LARGOS / VESTIDOS MIDIS.
            "robe courte", "robes courtes",        # FR: vestido corto
            "mini robe",                            # FR: mini vestido
            "kurzes kleid", "kurze kleider",        # DE: vestido corto
            "vestito corto", "vestiti corti",       # IT: vestido corto
        ]
    },
    
    "VESTIDOS MIDIS": {
        "type": "concrete",
        "keywords": [
            # Español
            "vestido midi", "vestidos midis",
            # Inglés
            "midi dress",
            "vestido medio", "medium dress",
            # Descripción ES
            "vestido rodilla", "knee length dress",
            # FIX (15/06/2026 — CH-multilang): keywords FR/DE/IT para vestidos MIDIS.
            "robe mi-longue", "robe midi",          # FR: vestido midi / semilong
            "midi kleid", "midi-kleid",             # DE: vestido midi
            "vestito midi",                         # IT: vestido midi
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
            # FIX (13/06/2026 — CH-multilang)
            "jupe", "jupes",        # FR: falda
            "rock", "röcke",        # DE: falda (nota: "rock" también EN, contexto ayuda)
            "gonna", "gonne",       # IT: falda
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
            # FIX (13/06/2026 — CH-multilang)
            "haut", "hauts",        # FR: top/blusa
            "chemise", "chemises",  # FR: camisa
            "oberteil",             # DE: parte superior/top
            "bluse", "blusen",      # DE: blusa
            "maglia", "maglie",     # IT: jersey/top
            "camicetta",            # IT: blusa
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
        # FIX (11/04/2026): ACCESSORIES era 'concrete' pero ningún producto
        # real tiene product_type=='ACCESSORIES'. El catálogo usa nombres
        # específicos: AROS, COLLARES, BRAZALETES, CLUTCH, CINTURONES, etc.
        # Convirtiendo a 'parent' el sistema expande automáticamente a los
        # product_types reales cuando el usuario dice 'accesorios'.
        "type": "parent",
        # FIX (06/07/2026): alineado con la colección real "Complementos" de
        # Shopify (confirmado via captura de pantalla, 9 tipos: BRAZALETE,
        # ALAS DE NOVIA, AROMAS, AROS, CARTERAS, CINTURONES, CLUTCH, COLLARES,
        # TOCADOS). Dos cambios respecto a la version anterior:
        #
        #   1. AGREGADO "BRAZALETE" (singular, 1 producto en catalogo real) --
        #      antes solo estaba "BRAZALETES" (plural, 36 productos). El
        #      producto singular nunca se beneficiaba de la expansion a
        #      categorias hermanas en F-08/F-08C.
        #
        #   2. AGREGADO "ALAS DE NOVIA" -- presente en Complementos pero
        #      ausente de esta lista; mismo problema que BRAZALETE singular.
        #
        #   3. ELIMINADO "BRALETTES" -- investigacion de estandar de industria
        #      (taxonomia de Google Shopping Merchant Center: los bralettes
        #      se clasifican bajo Apparel & Accessories > Clothing > Underwear
        #      & Socks > Bras, categoria 214 -- NUNCA bajo Accessories) confirma
        #      que un bralette es una PRENDA (cubre el torso, reemplaza a un
        #      top) y no un accesorio (los accesorios complementan una prenda
        #      ya puesta: joyeria, bolsos, cinturones, tocados). Ademas,
        #      BRALETTES ni siquiera pertenece a la coleccion Complementos en
        #      Shopify -- es su propio product_type separado. Ya esta
        #      correctamente clasificado como "top" en
        #      visual_retriever.py::SHOPIFY_TYPE_TO_OUTFIT_CATEGORY; estaba
        #      duplicado e inconsistente aqui. Ver DCT sesion 06/07/2026 para
        #      el analisis completo (Notion, DCT F-08 Fase A).
        #
        #   NOTA: AROMAS permanece deliberadamente ausente de esta lista --
        #   ver NON_FASHION_CATEGORIES_UPPER mas abajo (un perfume no es una
        #   prenda/accesorio vestible, exclusion ya validada el 28/06/2026).
        "subcategories": [
            "AROS", "COLLARES", "BRAZALETES", "BRAZALETE",
            "CLUTCH", "CINTURONES", "CARTERAS",
            "TOCADOS", "ALAS DE NOVIA",
        ],
        "keywords": [
            # Español genérico
            "accesorio", "accesorios",
            # Inglés
            "accessory", "accessories",
            # Complemento
            "complemento", "complementos",
            # Descriptivos
            "detalle", "detalles",
            # FIX (14/06/2026 — CH-multilang): sin estas keywords, "Montre-moi
            # des accessoires" no detecta ACCESSORIES → retorna KIMONOS del contexto.
            "accessoire", "accessoires",   # FR: accesorio/s
            "bijou", "bijoux",             # FR: joya/s (colectivo)
            "Accessoire", "Accessoires",   # DE: accesorio/s
            "Schmuck",                     # DE: joyería
            "accessorio", "accessori",     # IT: accesorio/s
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
    
    # -----------------------------------------------------------------------
    # FIX (11/04/2026): Patrones relacionales para penalizar categorias de contexto.
    # En "Que accesorios combinan con este vestido?", 'vestido' es contexto,
    # no intencion. Las categorias DESPUES del marcador relacional reciben
    # specificity=0.1 para quedar al final de la lista y no afectar el reparto.
    # -----------------------------------------------------------------------
    RELATIONAL_PATTERNS = [
        r'combina[rn]?\s+con',
        r'combinen?\s+con',
        r'que\s+va[yn]a?\s+con',
        r'van\s+con',
        r'va\s+con',
        r'para\s+(?:este|esta|ese|esa|un|una|el|la)\b',
        r'con\s+(?:este|esta|ese|esa|el|la)\b',
        r'que\s+combine[n]?\s+con',
        r'que\s+pegue[n]?\s+con',
        r'que\s+quede[n]?\s+con',
        r'similar(?:es)?\s+a\s+este',
        r'parecidos?\s+a\s+este',
    ]
    relational_cutoff_pos = None
    for _pat in RELATIONAL_PATTERNS:
        _m = re.search(_pat, query_normalized)
        if _m:
            relational_cutoff_pos = _m.start()
            logger.debug(f"Relational pattern '{_pat}' at pos {relational_cutoff_pos}")
            break

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
                # Calcular especificidad (keywords mas largos = mas especificos)
                specificity = len(keyword.split())  # Numero de palabras
                
                # FIX (11/04/2026): Si el keyword aparece DESPUES del marcador
                # relacional, es categoria de contexto. Penalizar a 0.1.
                _kw_match = re.search(pattern, query_normalized)
                if (
                    relational_cutoff_pos is not None
                    and _kw_match is not None
                    and _kw_match.start() > relational_cutoff_pos
                ):
                    specificity = 0.1
                    logger.debug(
                        f"Context cat '{category}' (kw:'{keyword}') penalized "
                        f"after relational marker at pos {relational_cutoff_pos}"
                    )
                
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
    
    # FIX (28/05/2026 — diversificacion): Si una subcategoria fue detectada
    # explicitamente en la query (specificity > 0.5 = keyword concreto de 2+ palabras),
    # suprimir las hermanas que solo entraron por expansion del padre (specificity = 0.5).
    # Ejemplo: "vestidos cortos" -> mantener solo VESTIDOS CORTOS, quitar
    # VESTIDOS LARGOS / VESTIDOS MIDIS que entraron via parent VESTIDOS.
    # Sin este filtro: reparto 3:3:2 aunque el usuario pidio explicitamente vestidos cortos.
    if detected_categories:
        for _par_name, _par_cfg in CATEGORY_KEYWORDS.items():
            if _par_cfg.get("type") != "parent":
                continue
            _subcats = _par_cfg.get("subcategories", [])
            # Subcategorias con deteccion concreta alta (detectadas directamente, no via padre)
            _concrete_high = [s for s in _subcats if detected_categories.get(s, 0) > 0.5]
            if _concrete_high:
                # Eliminar hermanas que solo entraron via expansion del padre (specificity = 0.5)
                for _sibling in _subcats:
                    if _sibling not in _concrete_high and detected_categories.get(_sibling, 0) <= 0.5:
                        detected_categories.pop(_sibling, None)

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
    exclude_products: Optional[Set[str]] = None,
    strict_category: bool = False,  # DECISION (19/06/2026): coherencia categorica estricta, Caso A
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
        strict_category: si True, el paso 6 (relleno con CUALQUIER categoria del
            catalogo cuando las categorias pedidas no alcanzan n) se omite --
            devuelve menos de n en vez de mezclar categorias no solicitadas.
            Usado para queries de categoria explicita ("muestrame calzones") donde
            el usuario tiene un interes especifico y mezclar no tiene sentido
            (DECISION 19/06/2026, Caso A). Default False preserva el comportamiento
            existente para callers que no lo especifiquen.
        
    Returns:
        List[Dict]: Lista de n productos distribuidos entre categorías
    """
    if not products or not categories or n <= 0:
        return []
    
    if exclude_products is None:
        exclude_products = set()
    
    # 1. Filtrar productos disponibles (excluir vistos)
    # FIX (20/06/2026): tambien excluir gift cards y similares (ver
    # is_recommendable_product) -- no son articulos de moda recomendables.
    available_products = [
        p for p in products 
        if str(p.get("id", "")) not in exclude_products
        and is_recommendable_product(p)
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
    
    # 6. Si no alcanzamos n productos, rellenar con productos de cualquier categoria.
    # FIX (19/06/2026 -- strict_category, Caso A): este relleno tomaba productos
    # de CUALQUIER categoria del catalogo (available_products no esta filtrado por
    # las categorias pedidas) cuando las categorias detectadas en la query no
    # alcanzaban n. Resultado real observado: "muestrame calzones" con pocos
    # calzones disponibles devolvia calzones + productos random sin relacion,
    # sin avisar al usuario. DECISION (19/06/2026): si el usuario nombro una
    # categoria especifica, mezclar no tiene sentido -- mejor devolver menos de n.
    if len(selected_products) < n and not strict_category:
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
    elif len(selected_products) < n and strict_category:
        logger.info(
            f"🔄 strict_category=True: NO se rellena con otras categorias. "
            f"Devolviendo {len(selected_products)}/{n} sin completar."
        )
    
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


def normalize_recommendation_dict(
    raw: Dict,
    rank: int = 0,
    score_start: float = 1.0,
    score_step: float = 0.02,
    source: str = "unknown",
) -> Dict:
    """
    Normaliza cualquier dict de producto al esquema visual canonico.

    Los cuatro bloques de recomendacion visual (F-08 Fase A, F-08C camino
    feliz, F-08C candidatos parciales, F-08C relleno categorizado) construian
    cada uno su propio dict con los mismos 8 campos pero copiando el codigo
    de forma manual. Esta funcion unifica esa logica en un unico lugar.

    El score sigue una progresion descendente:
        score = round(score_start - rank * score_step, 4)
    Cada bloque caller pasa el rank (posicion dentro de su propia lista) y
    el score_start apropiado para que la progresion nunca se solape entre
    fuentes distintas en una misma respuesta hibrida.

    Args:
        raw:         Dict crudo del catalogo (de id_index) o dict plano de
                     smart_fallback -- ambos tienen al menos id/title/handle.
        rank:        Posicion 0-indexed dentro de la lista de resultados.
        score_start: Score del primer elemento de esta fuente (default 1.0).
        score_step:  Decremento por posicion (default 0.02).
        source:      Etiqueta de trazabilidad (ej. 'visual_search_f08',
                     'visual_diversification_f08c', 'categorized_fill_f08c').

    Returns:
        Dict con los campos: id, title, similarity_score, score, handle,
        image_url, product_data, source.
    """
    score = round(score_start - rank * score_step, 4)
    return {
        "id":               str(raw.get("id", "")),
        "title":            raw.get("title", "") or "Producto",
        "similarity_score": score,
        "score":            score,
        "handle":           raw.get("handle", ""),
        "image_url":        raw.get("image_url"),
        # Anidar el dict crudo para que los consumidores downstream
        # (mcp_personalization_engine, sanitize_rec_for_frontend) puedan
        # acceder a todos los campos del catalogo sin doble lookup.
        "product_data":     raw,
        "source":           source,
    }


def is_recommendable_product(product: Dict) -> bool:
    """
    Determina si un producto es apto para aparecer en recomendaciones de
    fallback (popular, diverso, por categoria). Excluye gift cards y otros
    items no-fisicos que no deberian recomendarse como articulos de moda.

    FIX (20/06/2026): Gift Card (ID 9977923600693) aparecio en
    recomendaciones de relleno via "Standard diversification" -- sin
    imagen, CHF 0.01 (conversion desde 10 CLP, precio nominal tipico de
    gift card). Las 4 estrategias de fallback samplean sobre el catalogo
    completo sin distinguir tipo de producto; este filtro centraliza la
    exclusion para las 4 a la vez, en el mismo punto donde ya se filtra
    por exclude_products.

    Senales usadas (en orden de prioridad):
      1. product.get("gift_card") is True -- campo booleano nativo de
         Shopify, presente si el catalogo lo preservo al sincronizar.
      2. "gift card" / "tarjeta de regalo" en el titulo (case-insensitive)
         -- senal robusta y especifica para este catalogo de moda; ningun
         producto de ropa legitimo tendria esas palabras en el titulo.
      3. "snowboard" en el titulo (case-insensitive) -- FIX (26/06/2026):
         "The Inventory Not Tracked Snowboard" (ID 9977923633461) y "The
         Multi-managed Snowboard" (ID 9977924124981) se mostraron a clientes
         reales como recomendaciones de moda, via la rama de relleno aleatorio
         "Standard diversification". Son productos de demostracion que Shopify
         precarga en toda tienda nueva (nomenclatura fija "The [X] Snowboard").
         Se evaluo excluir por ausencia de market_prices (senal mas robusta,
         confirmada via el warning [OpcionA-fallback] en produccion), pero se
         descarto: ese campo no se popula de forma persistente en el catalogo
         maestro (el batch de enriquecimiento de PASO 4.5 esta desactivado
         desde 21/04/2026, y el enriquecimiento lazy por turno opera sobre
         copias que no se propagan de vuelta) -- excluir por su ausencia
         hubiera afectado a la mayoria del catalogo, no solo a los snowboards.

    Args:
        product: dict crudo del catalogo (de products / product_data).

    Returns:
        bool: True si el producto es apto para recomendar, False si debe
        excluirse de cualquier lista de recomendaciones de fallback.
    """
    if product.get("gift_card") is True:
        return False
    title = (product.get("title") or "").lower()
    if "gift card" in title or "tarjeta de regalo" in title:
        return False
    if "snowboard" in title:
        return False
    return True


# FIX (28/06/2026): categorias que son productos legitimos y vendibles, pero
# NO son prendas/accesorios de moda vestibles -- recomendarlas como "similar"
# a ropa confunde al usuario (ej. un perfume sugerido como similar a un
# pantalon). Confirmado contra el catalogo real de Shopify: dentro de la
# coleccion "Complementos" (9 product_type: BRAZALETE, ALAS DE NOVIA, AROMAS,
# AROS, CARTERAS, CINTURONES, CLUTCH, COLLARES, TOCADOS), AROMAS es el UNICO
# no vestible -- los otros 8 son accesorios de moda legitimos (pulseras, aros,
# carteras, cinturones, collares, tocados, velos). Evidencia real (sesion
# 28/06/2026): "Aroma Frutos Rojos 100 ml" recomendado como "producto similar"
# a un Palazzo (pantalon), via la rama de relleno aleatorio "Standard
# diversification" en get_diverse_category_products().
#
# Nota: reorganizar estas categorias en Shopify (ej. crear una coleccion
# "Perfumeria" separada) es una decision de merchandising independiente de
# este fix -- las colecciones de Shopify no cambian el campo product_type de
# cada producto, que es lo que este sistema usa para agrupar por categoria.
# Este set debe actualizarse si en el futuro aparecen mas product_type no
# vestibles (ej. velas, joyeria de regalo no vestible, etc.).
NON_FASHION_CATEGORIES_UPPER = {"AROMAS"}


def _score_product_quality(product: Dict) -> float:
    """
    Score heuristico de calidad de un producto -- usado para PRIORIZAR
    seleccion (en vez de azar puro) cuando se rellena con productos de
    diversificacion/relleno.

    FIX (27/06/2026): extraido como helper compartido a partir del scoring
    que ya existia, en linea, dentro de get_popular_products(). Se reusa
    ahora tambien en get_diverse_category_products() para dar peso de
    calidad a la seleccion de PRODUCTOS dentro de cada categoria (no a la
    seleccion de QUE categorias incluir, que sigue siendo aleatoria por
    diseno -- esa aleatoriedad es la diversificacion en si).

    DECISION (27/06/2026): se elimino la senal de banda de precio que existia
    en la version original (+1 si 10<=precio<=100, -1 si precio<=0). Esa banda
    compara contra el precio CRUDO en CLP -- los productos reales de este
    catalogo convierten a CHF 4-223 (~4.500-250.000 CLP), muy por encima de
    ese rango. La senal no discriminaba nada en la escala actual (ni
    productos reales ni los productos de demostracion de Shopify la
    activaban), asi que se descarto en vez de recalibrar un numero magico
    nuevo que podria volver a desincronizarse con la escala real del catalogo.

    Señales usadas: imagenes (+2), descripcion >100 caracteres (+1),
    mas de 1 variante (+1), tiene tags (+1), mas jitter aleatorio (+/-0.5)
    para mantener variedad entre llamadas (sin esto, el resultado seria
    100% deterministico turno a turno).

    Returns:
        float: score heuristico, mayor = mejor candidato.
    """
    score = 0.0

    if product.get("images") and len(product.get("images", [])) > 0:
        score += 2

    description = product.get("body_html", "") or product.get("description", "")
    if description and len(description) > 100:
        score += 1

    if product.get("variants") and len(product.get("variants", [])) > 1:
        score += 1

    if product.get("tags") and len(product.get("tags", [])) > 0:
        score += 1

    score += random.uniform(-0.5, 0.5)

    return score


def _pick_top_by_quality(products: List[Dict], n: int) -> List[Dict]:
    """
    Selecciona los n productos de mayor score de calidad (ver
    _score_product_quality), en vez de random.sample() puro.

    FIX (27/06/2026): usado en get_diverse_category_products() para las 4
    llamadas que seleccionan PRODUCTOS (no categorias) -- ver docstring de
    _score_product_quality para el razonamiento completo. Si n >= len(products)
    no hay nada que priorizar, se devuelven todos sin reordenar (evita gastar
    ciclos de sort innecesarios cuando no hay exceso de candidatos).

    Args:
        products: lista de productos candidatos.
        n: cuantos devolver (los de mayor score).

    Returns:
        List[Dict]: los n productos de mayor score, mismo esquema de entrada.
    """
    if n >= len(products):
        return list(products)
    scored = [(p, _score_product_quality(p)) for p in products]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored[:n]]


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
            
        # FIX (20/06/2026): tambien excluir gift cards y similares (ver
        # is_recommendable_product) -- no son articulos de moda recomendables.
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
            and is_recommendable_product(p)
        ]
        
        if not available_products:
            # FIX (18/06/2026 - BUG-NREC-3 / Bug 6, hallado durante la validacion de
            # BUG-NREC-2): el bloque anterior tenia un "ultimo recurso" que, cuando
            # el catalogo quedaba completamente agotado por las exclusiones
            # (len(products) <= len(exclude_products)), ignoraba exclude_products
            # por completo y tomaba products[:n] del catalogo SIN FILTRAR. Esto
            # podia reintroducir productos que el caller (ej. get_diverse_category_products,
            # via su propio "ultimo recurso") acababa de seleccionar segundos antes
            # en la misma llamada, generando duplicados en el resultado final.
            # Reproducido deterministicamente: products=4, exclude=4 -> resultado
            # con un ID repetido (['P1','P3','P4','P1']).
            #
            # FIX: preferimos devolver menos de n productos (visible en logs) a
            # violar silenciosamente la exclusion. available_products se queda
            # vacio; el flujo normal de abajo (scored_products=[], sorted=[],
            # popular_products=[]) ya devuelve [] de forma honesta sin necesidad
            # de un return temprano.
            logger.warning(
                "No hay productos disponibles despues de excluir las interacciones del usuario "
                "(catalogo agotado por exclusiones) - devolviendo lista vacia en vez de ignorar exclusiones"
            )
        
        # FIX (27/06/2026): scoring extraido a _score_product_quality() (helper
        # compartido, reusado tambien en get_diverse_category_products()). Se
        # elimino la senal de banda de precio (+1 si 10<=precio<=100, -1 si
        # precio<=0) -- comparaba contra el precio CRUDO en CLP, fuera de
        # escala para el catalogo real actual (CHF 4-223 ~= 4.500-250.000 CLP).
        # Ver docstring de _score_product_quality para el detalle completo.
        scored_products = [
            (product, _score_product_quality(product))
            for product in available_products
        ]
        
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
                "handle": product.get("handle", ""),
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
            
        # FIX (20/06/2026): tambien excluir gift cards y similares (ver
        # is_recommendable_product) -- no son articulos de moda recomendables.
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
            and is_recommendable_product(p)
        ]
        
        if not available_products:
            # FIX (18/06/2026 - BUG-NREC-3 / Bug 6): mismo patron que en
            # get_popular_products. El bloque anterior recalculaba el mismo filtro
            # que ya habia dado vacio (non_excluded era, por construccion, identico
            # a available_products) y, al ser siempre vacio, caia al
            # "else: random.sample(products, ...)" que ignoraba exclude_products
            # por completo. Devolver [] aqui es honesto y consistente con el otro
            # guard de esta misma funcion (catalogo vacio -> return []).
            logger.warning(
                "No hay productos disponibles despues de excluir las interacciones del usuario "
                "(catalogo agotado por exclusiones) - devolviendo lista vacia en vez de ignorar exclusiones"
            )
            return []
        
        # Agrupar productos por categoría
        # FIX (28/06/2026): excluir categorias no vestibles (ver
        # NON_FASHION_CATEGORIES_UPPER) ANTES de construir el pool de
        # diversificacion -- asi nunca pueden ser elegidas ni por "smart
        # diversification" ni por "standard diversification", sin importar
        # cual de las dos ramas termine usandose.
        products_by_category = {}
        for product in available_products:
            category = product.get("product_type", "General")
            if category.upper() in NON_FASHION_CATEGORIES_UPPER:
                continue
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
                            # FIX (27/06/2026): peso de calidad en vez de azar puro --
                            # ver _pick_top_by_quality. Solo cambia QUE PRODUCTO
                            # representa la categoria, no QUE categorias se incluyen.
                            selected = _pick_top_by_quality(category_products, num_to_take)
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
                                    # FIX (27/06/2026): peso de calidad, ver arriba.
                                    selected = _pick_top_by_quality(category_products, num_to_take)
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
                            "handle": product.get("handle", ""),
                            # FIX (19/06/2026 -- bug de imagen faltante en relleno):
                            # esta rama construia el dict campo por campo y se
                            # olvidaba de copiar image_url, a diferencia de las
                            # otras 3 estrategias de fallback que preservan el
                            # producto completo via **product. Resultado real
                            # observado: productos de relleno (otras categorias)
                            # se mostraban sin imagen en el widget.
                            "image_url": product.get("image_url"),
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
                # FIX (27/06/2026): peso de calidad en vez de azar puro -- ver
                # _pick_top_by_quality. selected_categories sigue siendo aleatoria
                # (diversificacion real); solo cambia el producto dentro de cada una.
                selected_products = _pick_top_by_quality(category_products, num_to_take)
                diverse_products.extend(selected_products)
        
        # Complementar si falta
        if len(diverse_products) < n:
            remaining_products = []
            for category in categories:
                if category not in selected_categories:
                    remaining_products.extend(products_by_category[category])
            
            num_additional = min(n - len(diverse_products), len(remaining_products))
            if num_additional > 0:
                # FIX (27/06/2026): peso de calidad en vez de azar puro -- este
                # pool junta productos de varias categorias NO seleccionadas, pero
                # sigue siendo seleccion de PRODUCTOS individuales, no de categorias.
                additional_products = _pick_top_by_quality(remaining_products, num_additional)
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
                "handle": product.get("handle", ""),
                # FIX (19/06/2026 -- bug de imagen faltante en relleno): mismo
                # patron que la rama "smart diversification" de arriba -- esta
                # rama tampoco copiaba image_url al construir el dict a mano.
                "image_url": product.get("image_url"),
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
        user_query: Optional[str] = None,  # ✨ NUEVO PARÁMETRO
        strict_category: bool = False,  # DECISION (18/06/2026): coherencia categorica estricta
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
            strict_category: si True, el top-up de PRIORIDAD 2 (cuando las
                categorias preferidas se agotan) NO amplia la busqueda al
                catalogo completo -- devuelve menos de n en vez de mezclar
                categorias. Usado por F-08C fill (18/06/2026) para garantizar
                coherencia categorica estricta. Default False preserva el
                comportamiento existente para todos los demas callers
                (flujo principal, F-08B.2 outfit completion).
            
        Returns:
            List[Dict]: Lista de productos recomendados con scores
        """
        if exclude_products is None:
            exclude_products = set()
        
        # Filtrar productos disponibles
        # FIX (20/06/2026): tambien excluir gift cards y similares (ver
        # is_recommendable_product) -- no son articulos de moda recomendables.
        available_products = [
            p for p in products 
            if str(p.get("id", "")) not in exclude_products
            and is_recommendable_product(p)
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

            # FIX (28/05/2026 — diversificacion): En queries "similares a este/esta",
            # anclar las categorias detectadas al producto que el usuario esta viendo.
            # Semantica: "este" = el producto actual → su categoria es la fuente de verdad.
            # Ejemplo: usuario en VESTIDOS CORTOS + "vestidos similares a este" →
            # query_categories original = ['VESTIDOS LARGOS', 'VESTIDOS CORTOS', 'VESTIDOS MIDIS']
            # despues del anchor = ['VESTIDOS CORTOS'] (desde user_events primary)
            # Guarda: solo ancla si el contexto confirma una categoria ya detectada;
            # si el usuario pide una categoria DISTINTA (ej. "vestidos largos similares"),
            # la Change 1 ya habra filtrado a esa categoria y el anchor no cambia nada.
            if query_categories and user_events:
                _SIMILAR_THIS_RE = re.compile(
                    r'similar(?:es)?\s+a\s+(?:este|esta|esto|estos|estas)\b|'
                    r'parecido[sa]?\s+a\s+(?:este|esta)\b|'
                    r'\bcomo\s+(?:este|esta)\b',
                    re.IGNORECASE
                )
                if _SIMILAR_THIS_RE.search(user_query):
                    _primary_upper = {
                        e.get("product_info", {}).get("product_type", "").upper()
                        for e in user_events
                        if e.get("product_info", {}).get("source") == "current_product_context"
                    }
                    _anchored = [c for c in query_categories if c.upper() in _primary_upper]
                    if _anchored:
                        query_categories = _anchored
                        logger.info(
                            f"FIX anchor: 'similar a este' anchored to context: {query_categories}"
                        )

            if query_categories:
                logger.info(f"🎯 MULTI-CATEGORY QUERY-DRIVEN: Detected {len(query_categories)} categories")
                logger.info(f"   Categories: {query_categories}")
                logger.info(f"   Prioritizing query-detected categories over historical preferences")
                
                # Usar sampling inteligente para distribuir entre categorías
                query_driven_products = smart_sample_across_categories(
                    products=available_products,
                    categories=query_categories,
                    n=n,
                    exclude_products=exclude_products,
                    strict_category=strict_category,  # DECISION (19/06/2026): Caso A
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
                            # FIX (27/03/2026): sobrescribir price explicitamente.
                            # **product puede traer price=None (catalogo TF-IDF crudo).
                            # safe_extract_price() sube variants[0].price al nivel
                            # raiz si price es None o 0, garantizando que
                            # sanitize_rec_for_frontend y ProductCard.tsx reciban
                            # el valor correcto incluso si tfidf aun no fue
                            # reentrenado con _normalize_product_price.
                            "price": safe_extract_price(product),
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

                # FIX (10/04/2026): normalizar a uppercase para comparar con product_type
                preferred_categories_upper = [cat.upper() for cat in preferred_categories]
                logger.info(f"   Preferred categories (normalized): {preferred_categories_upper}")

                # Cuantas categorias tienen productos reales (para calcular sample_size)
                # FIX (21/04/2026 — BUG-NREC-3): antes sample_size=min(3,...) hardcodeado.
                # Si solo 1 categoria matchea, 3 << n=8. Ahora usamos ceil(n/n_cats_reales).
                n_cats_with_products = len([
                    c for c in preferred_categories_upper
                    if any(p.get("product_type", "").upper() == c for p in available_products)
                ])

                # Generar recomendaciones de categorías preferidas
                personalized_products = []

                for category in preferred_categories_upper:
                    category_products = [
                        p for p in available_products
                        if p.get("product_type", "").upper() == category
                    ]

                    if category_products:
                        # Ceil division: garantiza que la suma cubra n cuando hay pocas categorias
                        per_cat = max(1, -(-n // max(n_cats_with_products, 1)))
                        sample_size = min(per_cat, len(category_products))
                        sampled = random.sample(category_products, sample_size)
                        personalized_products.extend(sampled)

                # Si tenemos productos personalizados
                if personalized_products:
                    # Limitar a n primero
                    personalized_products = personalized_products[:n]

                    # FIX (21/04/2026 — BUG-NREC-3 cont.): Top-up garantizado.
                    # Si las categorias preferidas tienen pocos productos tras exclusiones,
                    # rellenar con disponibles priorizando categorias afines primero.
                    #
                    # FIX (28/05/2026 — diversificacion): Top-up afinado.
                    # ANTES: remaining = todos los disponibles → accesorios 0.01 CHF rellenaban
                    # los slots cuando CONJUNTOS FALDAS se agotaba.
                    # AHORA: preferred_remaining = productos de las mismas preferred_categories
                    # (expandidas con hermanas via get_parent_categories en el handler).
                    # Solo va broad cuando preferred_categories se agotan completamente.
                    if len(personalized_products) < n:
                        needed = n - len(personalized_products)
                        used_ids = {str(p.get("id", "")) for p in personalized_products}
                        remaining = [
                            p for p in available_products
                            if str(p.get("id", "")) not in used_ids
                        ]
                        if remaining:
                            # Prioridad 1 del top-up: productos de las mismas categorias preferidas
                            preferred_remaining = [
                                p for p in remaining
                                if p.get("product_type", "").upper() in preferred_categories_upper
                            ]
                            if preferred_remaining:
                                extra = random.sample(
                                    preferred_remaining, min(needed, len(preferred_remaining))
                                )
                                logger.info(
                                    f"   Top-up P2 (preferred): {len(extra)} products "
                                    f"from preferred categories (pool={len(preferred_remaining)})"
                                )
                                personalized_products.extend(extra)
                            elif not strict_category:
                                # Prioridad 2 del top-up: categorias preferidas agotadas,
                                # diversificar al catalogo completo
                                extra = random.sample(remaining, min(needed, len(remaining)))
                                logger.info(
                                    f"   Top-up P2 (broad): {len(extra)} products "
                                    f"(preferred exhausted, pool={len(remaining)})"
                                )
                                personalized_products.extend(extra)
                            else:
                                # FIX (18/06/2026 - strict_category): decision de producto.
                                # Coherencia categorica estricta tiene prioridad sobre
                                # completar n. NO hacer broadening -- devolver menos de n.
                                # El caller (F-08C) detecta el deficit comparando contra
                                # lo pedido y notifica al usuario via
                                # mcp_context.category_exhausted_info, en vez de mostrar
                                # otras categorias sin avisar.
                                logger.info(
                                    f"   Top-up P2 (strict_category=True): preferred "
                                    f"exhausted, NO broadening. Devolviendo "
                                    f"{len(personalized_products)}/{n} sin completar."
                                )

                    # Agregar scores
                    recommendations = []
                    for i, product in enumerate(personalized_products):
                        score = 0.9 - (i * 0.4 / max(len(personalized_products), 1))
                        recommendations.append({
                            **product,
                            "price": safe_extract_price(product),
                            "score": score,
                            "recommendation_type": "personalized_fallback",
                            "based_on_categories": preferred_categories,
                        })

                    logger.info(f"\u2705 Generated {len(recommendations)} personalized recommendations")
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
        user_query: Optional[str] = None,  # ✨ NUEVO PARÁMETRO
        strict_category: bool = False,  # DECISION (18/06/2026): propagar a get_personalized_fallback
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
            strict_category: si True, propaga a get_personalized_fallback para
                que su top-up de PRIORIDAD 2 no amplie a otras categorias cuando
                las preferidas se agoten. Ver docstring de get_personalized_fallback.
            
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
        
        # ✨ PRIORIZAR: Si hay query con categoría o hay eventos del usuario, usar
        # personalized_fallback (que detecta categoría desde la query y/o desde los
        # eventos). Antes había DOS llamadas casi idénticas a get_personalized_fallback
        # -- una para "hay query" y otra para "hay eventos sin query" -- y solo la
        # primera pasaba exclude_products=combined_exclude (FIX BUG-NREC-1, 21/04/2026).
        #
        # FIX (17/06/2026 — BUG-NREC-2 / "Bug 5" del sprint F-08C Candidatos Parciales):
        # La segunda rama (user_events sin user_query) llamaba a get_personalized_fallback
        # SOLO con (user_id, products, user_events, n) -- sin exclude_products. Como
        # exclude_products tiene default None en get_personalized_fallback, esa rama
        # IGNORABA POR COMPLETO combined_exclude (vistos en turnos previos + cualquier
        # exclusion explicita del caller), pese a que combined_exclude ya se habia
        # calculado correctamente unas lineas arriba.
        #
        # IMPACTO REAL CONFIRMADO (reproducido y validado con caso de prueba ejecutable
        # antes de aplicar este fix): cualquier caller que use user_query=None +
        # user_events (patron usado por F-08B.2 outfit_completion, ya en produccion,
        # y por F-08C candidatos-parciales-mas-relleno) podia recibir productos
        # duplicados o ya mostrados en el "relleno", porque las exclusiones nunca
        # llegaban a get_personalized_fallback.
        #
        # FIX: unificar ambas ramas en una sola llamada. user_query=None es un valor
        # perfectamente valido para get_personalized_fallback (su PRIORIDAD 1 simplemente
        # no se activa si la query es None/vacia), asi que no hace falta mantener dos
        # llamadas casi-idénticas -- la duplicacion de código era la causa estructural
        # de que esta rama quedara desactualizada respecto al fix de BUG-NREC-1.
        # Con la unificacion, cualquier caller futuro que use este mismo patron queda
        # protegido automaticamente, sin depender de que alguien recuerde replicar
        # el fix en cada rama nueva.
        if user_query or (user_events and len(user_events) > 0):
            if user_query:
                logger.info(f"🎯 Using query-aware personalized fallback with query: '{user_query[:50]}...'")
            else:
                logger.info(f"Usando fallback personalizado para usuario {user_id} con {len(user_events)} eventos")
            return await ImprovedFallbackStrategies.get_personalized_fallback(
                user_id,
                products,
                user_events,
                n,
                exclude_products=combined_exclude,  # FIX (17/06/2026): pasar exclusiones reales SIEMPRE
                user_query=user_query,
                strict_category=strict_category,
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