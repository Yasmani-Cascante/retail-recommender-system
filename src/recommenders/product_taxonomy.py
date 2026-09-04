
# src/recommenders/product_taxonomy.py
"""
Fuente unica de verdad de taxonomia para ESTE tenant, usada por Composite
Embedding Granular (F-08/F-08C/F-08B).

Reemplaza (ver PLAN_Fase1b_Revision_Arquitectonica_23072026.md, Paso 1-2):
  - SHOPIFY_TYPE_TEXT_PROMPTS (visual_retriever.py) -- el embedding-service
    ya no necesita conocer taxonomia (Opcion B: texto resuelto aqui, en el
    monolito, enviado ya resuelto via boost_text).
  - _B08_SHOPIFY_TO_OUTFIT_CAT (antes inline en mcp_conversation_handler.py)

Para onboardear un tenant nuevo: este es el unico archivo a reescribir hoy.
Direccion futura (config por tenant en DB, derivacion por centroide de
catalogo en vez de texto escrito a mano): ver PLAN_Fase1b_Revision_Arquitectonica_23072026.md,
seccion 3 (explicitamente diferido, no construir todavia).
"""
from typing import Dict, List, Optional, TypedDict


class TypeTaxonomyEntry(TypedDict, total=False):
    outfit_slot: str            # bucket de search_outfit_by_image (requerido)
    steering_text: str          # texto para composite embedding (opcional --
                                 # solo tipos con prompt propio, hoy: familia ACCESSORIES)
    alpha_reinforce: float      # alpha para F-08/F-08C (reforzar propio tipo)
    alpha_complement: float     # alpha para F-08B (pedir tipo distinto)


PRODUCT_TAXONOMY: Dict[str, TypeTaxonomyEntry] = {
    # Familia ACCESSORIES -- con steering_text y alpha propios.
    # Prompts identicos a los ya validados en produccion (Fase 1, 19/07/2026)
    # y en fase0_poc.py -- no se reescriben, solo se centralizan.
    "AROS":          {"outfit_slot": "accessory", "steering_text": "earrings aros pendientes arete jewelry mujer", "alpha_reinforce": 0.5, "alpha_complement": 0.2},
    "COLLARES":      {"outfit_slot": "accessory", "steering_text": "necklace collar cadena gargantilla chain jewelry mujer", "alpha_reinforce": 0.3, "alpha_complement": 0.2},  # AJUSTADO (26/07/2026): bajado de 0.5 a 0.3 con evidencia real (fase0_poc.py, 2 anclas: Choker Alana 5->8/10, Collar Moneda 2->9/10 en alpha=0.3; costo de similitud visual pura minimo, -0.007 a -0.018 vs. plana). Direccion corregida respecto al comentario anterior -- mas peso de TEXTO (alpha mas bajo), no mas peso de imagen, es lo que ayuda cuando el atractor domina.
    "BRAZALETES":    {"outfit_slot": "accessory", "steering_text": "bracelet brazalete pulsera jewelry mujer", "alpha_reinforce": 0.3, "alpha_complement": 0.2},  # AJUSTADO (26/07/2026): bajado de 0.5 a 0.3, misma evidencia que COLLARES (fase0_poc.py, 2 anclas: Lucila 6->10/10 en 0.4 [10/10 empata en 0.3], Amparo Plateado 0->7/10 en alpha=0.3 -- este ultimo con atractor real hacia AROS confirmado por compute_anchor_type_affinities).
    "BRAZALETE":     {"outfit_slot": "accessory", "steering_text": "bracelet brazalete pulsera jewelry mujer", "alpha_reinforce": 0.3, "alpha_complement": 0.2},  # AJUSTADO (26/07/2026): igual a BRAZALETES (mismo steering_text, mismo tipo real).
    "CINTURONES":    {"outfit_slot": "accessory", "steering_text": "belt cinturon correa mujer", "alpha_reinforce": 0.3, "alpha_complement": 0.2},
    "TOCADOS":       {"outfit_slot": "accessory", "steering_text": "headpiece tocado diadema corona hair accessory mujer", "alpha_reinforce": 0.3, "alpha_complement": 0.2},
    "ALAS DE NOVIA": {"outfit_slot": "accessory", "steering_text": "bridal wings alas de novia veil wedding mujer", "alpha_reinforce": 0.5, "alpha_complement": 0.2},
    "CARTERAS":      {"outfit_slot": "bag", "steering_text": "handbag cartera bolso purse mujer", "alpha_reinforce": 0.5, "alpha_complement": 0.2},
    "CLUTCH":        {"outfit_slot": "bag", "steering_text": "clutch bag purse mujer", "alpha_reinforce": 0.5, "alpha_complement": 0.2},

    # Resto del catalogo -- solo outfit_slot (reemplaza _B08_SHOPIFY_TO_OUTFIT_CAT,
    # mapeo identico, ya verificado 1:1 contra el catalogo real el 11/07/2026).
    # Sin steering_text: search_outfit_by_image() sigue usando el prompt
    # generico del bucket (CATEGORY_TEXT_PROMPTS[outfit_slot]) para estos --
    # fuera de alcance de Fase 1b (fue validado solo para familia ACCESSORIES).
    "VESTIDOS CORTOS":     {"outfit_slot": "dress"},
    "VESTIDOS LARGOS":     {"outfit_slot": "dress"},
    "VESTIDOS MIDIS":      {"outfit_slot": "dress"},
    "ENTERITOS CORTOS":    {"outfit_slot": "enterito"},
    "ENTERITOS LARGOS":    {"outfit_slot": "enterito"},
    "TOPS":                {"outfit_slot": "top"},
    "BRALETTES":           {"outfit_slot": "top"},
    "PANTALONES":          {"outfit_slot": "bottom"},
    "FALDAS":              {"outfit_slot": "bottom"},
    "CAPAS BORDADAS":      {"outfit_slot": "outerwear"},
    "CAPAS GASA":          {"outfit_slot": "outerwear"},
    "KIMONOS":             {"outfit_slot": "outerwear"},
    "ZAPATOS":             {"outfit_slot": "shoes"},
    "CONJUNTOS FALDAS":     {"outfit_slot": "conjunto"},
    "CONJUNTOS PANTALONES": {"outfit_slot": "conjunto"},
    # AGREGADO (28/07/2026): confirmados via Shopify Admin API tras hallazgo
    # en produccion -- ancla VESTIDOS CORTOS + "que accesorios combinan" trajo
    # un NOVIAS CONJUNTOS PANTALONES colado en el bucket "accessory" (fail-open
    # de _b08_belongs_to_bucket() por tipo no catalogado). Nunca aparecio en la
    # auditoria del 26/07 -- ninguna de las variantes que se probo entonces
    # combinaba "NOVIAS" + "CONJUNTOS" + sufijo (se probo "NOVIAS CONJUNTOS"
    # a secas, que da 0 resultados; el tipo real siempre lleva el sufijo
    # FALDAS/PANTALONES). Confirmado tambien que CATEGORY_KEYWORDS
    # (improved_fallback_exclude_seen.py) ya los tenia registrados como
    # subcategorias de "CONJUNTOS" desde antes -- la deteccion por texto de
    # consulta ya funcionaba, el gap estaba solo en este archivo.
    "NOVIAS CONJUNTOS FALDAS":     {"outfit_slot": "conjunto"},
    "NOVIAS CONJUNTOS PANTALONES": {"outfit_slot": "conjunto"},

    # Linea NOVIAS (bridal) -- gap de cobertura confirmado 24/07/2026: no
    # estaba en el diccionario original (_B08_SHOPIFY_TO_OUTFIT_CAT) tampoco,
    # asi que un vestido de novia bien podia colarse sin bucket asignado.
    # AMPLIADO (26/07/2026) tras auditoria de cobertura contra el catalogo
    # real via Shopify Admin API (ver DCT_Fase1b..., Addendum 3, "Auditoria
    # de cobertura"): confirmados NOVIAS CORTOS y NOVIAS MIDIS como tipos
    # reales adicionales, mismo patron de 4 variantes por largo que VESTIDOS
    # (CORTOS/LARGOS/MIDIS + ENTERITOS). Los 4 NOVIAS_* ahora tienen cobertura
    # completa, verificada contra el catalogo real, no solo contra logs.
    "NOVIAS LARGOS":    {"outfit_slot": "dress"},
    "NOVIAS CORTOS":    {"outfit_slot": "dress"},
    "NOVIAS MIDIS":     {"outfit_slot": "dress"},
    "NOVIAS ENTERITOS": {"outfit_slot": "enterito"},
}


def get_steering_text(shopify_type: str) -> Optional[str]:
    """Texto de composite embedding para este tipo, o None si no tiene uno propio."""
    if not shopify_type:
        return None
    return PRODUCT_TAXONOMY.get(shopify_type.upper(), {}).get("steering_text")


def get_outfit_slot(shopify_type: str) -> Optional[str]:
    """Bucket de outfit-category (dress/top/bottom/shoes/accessory/bag/...) para este tipo."""
    if not shopify_type:
        return None
    return PRODUCT_TAXONOMY.get(shopify_type.upper(), {}).get("outfit_slot")


def get_alpha(shopify_type: str, mode: str) -> Optional[float]:
    """
    mode: 'reinforce' (F-08/F-08C, reforzar propio tipo del ancla) o
          'complement' (F-08B, pedir un tipo distinto al del ancla).
    """
    if not shopify_type:
        return None
    key = "alpha_reinforce" if mode == "reinforce" else "alpha_complement"
    return PRODUCT_TAXONOMY.get(shopify_type.upper(), {}).get(key)


def types_with_steering_text() -> List[str]:
    """Tipos con prompt de composite embedding propio (hoy: familia ACCESSORIES)."""
    return [t for t, e in PRODUCT_TAXONOMY.items() if "steering_text" in e]


def types_in_outfit_slot(outfit_slot: str) -> List[str]:
    """Todos los tipos Shopify que pertenecen a un bucket de outfit dado."""
    return [t for t, e in PRODUCT_TAXONOMY.items() if e.get("outfit_slot") == outfit_slot]
