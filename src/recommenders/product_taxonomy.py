
# src/recommenders/product_taxonomy.py
"""
Fuente unica de verdad de taxonomia para ESTE tenant, usada por Composite
Embedding Granular (F-08/F-08C/F-08B).

Reemplaza (ver PLAN_Fase1b_Revision_Arquitectonica_23072026.md, Paso 1-2):
  - SHOPIFY_TYPE_TEXT_PROMPTS (visual_retriever.py) -- el embedding-service
    ya no necesita conocer taxonomia (Opcion B: texto resuelto aqui, en el
    monolito, enviado ya resuelto via boost_text).
  - _B08_SHOPIFY_TO_OUTFIT_CAT (antes inline en mcp_conversation_handler.py)

DECISION DE UNIFICACION (26/09/2026, ver DCT_Fase1b_Composite_Embedding_F08B_
Cierre_24072026.md, Addendum 6, y taxonomy_centroid_audit.py motivo 2 sobre
datos reales del catalogo):
  - _B08_SHOPIFY_TO_OUTFIT_CAT y _B08B2_SHOPIFY_TO_OUTFIT_CAT (mcp_conversation_
    handler.py, f08b2_category_resolution.py) quedan RETIRADOS -- donde
    coincidian con este archivo, coincidian sin excepcion (confirmado por el
    script de auditoria); donde no, este archivo ya era mas completo (8 gaps
    contra 14). Ambos ahora llaman a get_outfit_slot()/types_in_outfit_slot()
    de aqui en vez de mantener copias propias.
  - _OUTFIT_COMPLEMENT_MAP (mcp_conversation_handler.py, F-08B.2) queda
    RETIRADO -- 19 de 29 tipos de prenda ya caian a su fallback generico de
    4 items; en la practica funcionaba como una version incompleta de "todo
    el bucket accessory+bag", que es exactamente lo que
    types_in_outfit_slot() ya resuelve, probado y en produccion.
  - CATEGORY_KEYWORDS (improved_fallback_exclude_seen.py) se mantiene
    SEPARADO, a proposito -- hace deteccion de categoria desde texto libre
    con sinonimos, un problema distinto a tipo->outfit_slot. No se fusiona.

MEJORA ESTRUCTURAL (27/09/2026, ver DCT_Cierre_Fase2_Unificacion_Taxonomia_
27092026.md): _B08_FULL_CANDIDATE_CATS (mcp_conversation_handler.py) era una
lista manual y separada de buckets candidatos para sugerencias GENERICAS de
"completa el outfit" (F-08B, sin categoria explicita pedida) -- distinta del
concepto de "que buckets existen" (eso ya lo resuelve PRODUCT_TAXONOMY). Al
agregar el bucket "intimates" (26/09/2026) nadie decidio explicitamente si
debia aparecer ahi o no -- quedo excluido por OMISION (la lista es anterior
al bucket), no por una decision consciente, aunque resulto ser la decision
correcta (mismo principio que "lingerie", ya excluido a proposito desde el
13/07/2026). Para que esto no vuelva a pasar en silencio, esa lista ahora se
CALCULA desde aqui (generic_suggestion_candidate_slots()) en vez de
mantenerse escrita a mano en otro archivo: un bucket nuevo en
PRODUCT_TAXONOMY aparece automaticamente en sugerencias genericas salvo que
se agregue explicitamente a GENERIC_SUGGESTION_EXCLUDED_SLOTS -- la omision
silenciosa deja de ser posible, cualquier exclusion queda documentada aqui
mismo.

Para onboardear un tenant nuevo: este es el unico archivo a reescribir hoy.
Direccion futura (config por tenant en DB, derivacion por centroide de
catalogo en vez de texto escrito a mano): ver PLAN_Fase1b_Revision_Arquitectonica_23072026.md,
seccion 3 (explicitamente diferido, no construir todavia).
"""
from typing import Dict, List, Optional, Set, TypedDict


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

    # AGREGADO (26/09/2026): 6 tipos reales confirmados por
    # taxonomy_centroid_audit.py (motivo 2, corrida contra el catalogo real
    # 26/09/2026) sin outfit_slot asignado -- 154 productos combinados sin
    # bucket. CHAQUETAS y LEGGINGS van con buckets ya existentes; CALZONES,
    # LENCERIA, REDUCTORES y PIJAMAS son un bucket nuevo ("intimates") --
    # no encajan de forma natural en ninguno de los existentes.
    "CHAQUETAS":  {"outfit_slot": "outerwear"},
    "LEGGINGS":   {"outfit_slot": "bottom"},
    "CALZONES":   {"outfit_slot": "intimates"},
    "LENCERIA":   {"outfit_slot": "intimates"},
    "REDUCTORES": {"outfit_slot": "intimates"},
    "PIJAMAS":    {"outfit_slot": "intimates"},
}

# AGREGADO (26/09/2026): tipos reales del catalogo que EXISTEN pero no son
# prendas "combinables" en el sentido de outfit completion (F-08B) -- no
# deberian tener outfit_slot. taxonomy_centroid_audit.py los excluye
# explicitamente de sus reportes de gap por esta lista, no por descuido.
NON_APPLICABLE_TYPES: Set[str] = {"AROMAS", "PACK"}


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


def is_non_applicable_type(shopify_type: str) -> bool:
    """
    True si el tipo es real (existe en el catalogo) pero no aplica al
    concepto de outfit_slot (ej. AROMAS, PACK) -- no es un gap de cobertura.
    """
    if not shopify_type:
        return False
    return shopify_type.upper() in NON_APPLICABLE_TYPES


# AGREGADO (27/09/2026): buckets que existen en PRODUCT_TAXONOMY pero se
# excluyen A PROPOSITO de las sugerencias GENERICAS de "completa el outfit"
# (F-08B, mcp_conversation_handler.py, cuando el usuario NO pidio una
# categoria explicita) -- decision de producto, no limitacion tecnica. Un
# bucket ausente de aqui SIEMPRE debe ser una decision consciente: si se
# agrega un bucket nuevo a PRODUCT_TAXONOMY y no se agrega aqui, aparecera
# en sugerencias genericas por defecto ("no excluido" = "incluido").
GENERIC_SUGGESTION_EXCLUDED_SLOTS: Set[str] = {
    # (26/09/2026, confirmado 27/09/2026): mismo principio que "lingerie",
    # ya excluido a proposito desde el 13/07/2026 -- LENCERIA/CALZONES/
    # REDUCTORES/PIJAMAS son ropa intima; sugerirla sin que el usuario la
    # pida explicitamente puede sentirse invasivo. No es un gap, es la
    # aplicacion correcta de un principio ya establecido, solo que "intimates"
    # no existia como bucket formal cuando se escribio ese principio.
    "intimates",
}
# NOTA (27/09/2026): "conjunto" (Gap 3, 13/07/2026) estuvo aqui y se retiro
# tras resolver la causa raiz de la preocupacion original -- no estaba
# integrado en _B08_SLOT_CONFLICTS (mcp_conversation_handler.py) como
# alternativa de prenda principal junto a dress/enterito/top/bottom, asi que
# un "conjunto" no conflictuaba con ellos ni viceversa. Con ese conflicto ya
# registrado, sugerir un conjunto para un ancla que SI conflictua (dress/top/
# bottom/enterito) queda excluido automaticamente por el sistema de
# conflictos -- la exclusion aqui ya no tenia ninguna razon activa detras.
# Ver DCT_Cierre_Fase2_Unificacion_Taxonomia_27092026.md, seccion 7.1, para
# el analisis completo. Nota para features futuras con filosofia distinta a
# F-08B (ej. una funcion de "Inspiracion" mencionada 27/09/2026, que
# explicitamente NO quiere restriccion de categoria y SI quiere incluir
# conjuntos): este conjunto (GENERIC_SUGGESTION_EXCLUDED_SLOTS) es especifico
# de la filosofia de F-08B (un ancla + complementos coherentes) -- no debe
# reusarse sin repensarlo para una feature con objetivos de diseno distintos.


def all_outfit_slots() -> List[str]:
    """Todos los buckets distintos definidos en PRODUCT_TAXONOMY."""
    return sorted({
        e["outfit_slot"] for e in PRODUCT_TAXONOMY.values() if e.get("outfit_slot")
    })


def generic_suggestion_candidate_slots() -> List[str]:
    """
    Buckets elegibles para sugerencias GENERICAS de "completa el outfit"
    (F-08B, sin categoria explicita pedida por el usuario) -- todos los
    buckets existentes, menos los marcados en GENERIC_SUGGESTION_EXCLUDED_SLOTS.

    Reemplaza a _B08_FULL_CANDIDATE_CATS (antes una lista manual y separada
    en mcp_conversation_handler.py) -- se deriva automaticamente de
    PRODUCT_TAXONOMY para que un bucket nuevo nunca quede incluido o
    excluido por omision silenciosa, como paso con "intimates" el
    26/09/2026 (resulto ser la exclusion correcta, pero nadie la decidio a
    proposito en su momento).
    """
    return [s for s in all_outfit_slots() if s not in GENERIC_SUGGESTION_EXCLUDED_SLOTS]
