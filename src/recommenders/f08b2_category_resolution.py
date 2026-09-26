"""
f08b2_category_resolution.py
==============================
Extraido de mcp_conversation_handler.py (bloque F-08B.2) el 25/09/2026,
como paso previo -- red de seguridad -- antes de la decision de unificacion
de taxonomia (ver DCT_Cierre_Fase1_Fase3_Estabilizacion_24092026.md, seccion
9, y Evaluacion_Integral_Sistema_16092026.md, seccion 13, punto 3).

Por que existe este modulo:
    La logica de "que categorias debe recomendar F-08B.2, dado lo que el
    usuario pidio y el tipo del ancla" vivia inline, embebida dentro de una
    funcion async de ~1800 lineas con decenas de variables de contexto
    compartido -- imposible de testear de forma aislada sin invocar toda la
    maquina de conversacion (Redis, TF-IDF, embedding-service, etc.).

    Se extrae aqui SIN CAMBIAR EL COMPORTAMIENTO -- mismo codigo, misma
    logica, solo movido a una funcion pura con firma explicita -- para poder
    escribir tests automatizados reales antes de la refactorizacion mayor de
    unificacion de taxonomia (roadmap Fase 2, item 4: "tests automatizados...
    antes de refactorizar nada grande").

    Las dependencias reales (extract_categories_from_query,
    get_concrete_categories, types_in_outfit_slot) se inyectan como
    parametros en vez de importarse directamente -- mantiene este modulo
    sin dependencias pesadas (sklearn, etc.) y trivialmente testeable con
    stubs simples, mientras el llamador real (mcp_conversation_handler.py)
    pasa las funciones reales sin cambiar su comportamiento.

Cubre los dos bugs reales encontrados y corregidos esta semana (20-21/09/2026),
mas el comportamiento original (mapa _OUTFIT_COMPLEMENT_MAP) que nunca cambio:
    1. Auto-referencia: la consulta menciona el tipo exacto del propio ancla
       ("esto aros" con ancla AROS) -- se filtra antes de mapear, no se trata
       como un pedido nuevo.
    2. Sobre-expansion: una categoria concreta unica y especifica ("aretes")
       se mapeaba a su bucket completo (todo "accessory") en vez de respetar
       la especificidad del pedido -- ahora se usa el tipo exacto sin expandir.
    3. Sin categoria explicita utilizable: comportamiento original sin
       cambios -- mapa _OUTFIT_COMPLEMENT_MAP keyed por el tipo del ancla,
       con su limitacion ya documentada (solo cubre tipos de PRENDA, nunca
       tuvo entradas para anclas de tipo ACCESORIO).

NOTA sobre deuda tecnica heredada (no resuelta aqui, a proposito):
    _B08B2_SHOPIFY_TO_OUTFIT_CAT es una duplicacion temporal y ya documentada
    de _B08_SHOPIFY_TO_OUTFIT_CAT (el diccionario homologo del bloque F-08B
    principal). _OUTFIT_COMPLEMENT_MAP es una CUARTA fuente de taxonomia
    activa, distinta de product_taxonomy.py, _B08_SHOPIFY_TO_OUTFIT_CAT y
    CATEGORY_KEYWORDS. Resolver esa duplicacion es, precisamente, el alcance
    de la decision de unificacion de taxonomia (Fase 2) -- este modulo no la
    resuelve, solo la hace segura de tocar cuando llegue el momento.
"""
from typing import Callable, List, Optional, Set


# Mismo diccionario usado hoy en mcp_conversation_handler.py (F-08B.2) --
# duplicado temporal de _B08_SHOPIFY_TO_OUTFIT_CAT (bloque F-08B principal),
# documentado como tal. NO se resuelve aqui -- ver docstring del modulo.
_B08B2_SHOPIFY_TO_OUTFIT_CAT = {
    "AROS": "accessory", "COLLARES": "accessory",
    "BRAZALETES": "accessory", "BRAZALETE": "accessory",
    "CINTURONES": "accessory", "TOCADOS": "accessory",
    "ALAS DE NOVIA": "accessory",
    "CARTERAS": "bag", "CLUTCH": "bag",
    "VESTIDOS CORTOS": "dress", "VESTIDOS LARGOS": "dress",
    "VESTIDOS MIDIS": "dress",
    "ENTERITOS CORTOS": "enterito", "ENTERITOS LARGOS": "enterito",
    "TOPS": "top", "BRALETTES": "top",
    "PANTALONES": "bottom", "FALDAS": "bottom",
    "CAPAS BORDADAS": "outerwear", "CAPAS GASA": "outerwear",
    "KIMONOS": "outerwear",
    "ZAPATOS": "shoes",
    "CONJUNTOS FALDAS": "conjunto",
    "CONJUNTOS PANTALONES": "conjunto",
}

# Mapa original de F-08B.2 (comportamiento sin cambios desde antes de esta
# semana) -- usado solo cuando no hay categoria explicita utilizable en la
# consulta. Limitacion ya documentada (17/07/2026): solo tiene entradas para
# tipos de PRENDA, nunca para tipos de ACCESORIO como ancla.
_OUTFIT_COMPLEMENT_MAP = {
    "KIMONOS":          ["AROS", "COLLARES", "CLUTCH", "CINTURONES", "BRAZALETES"],
    "TAPADOS":          ["AROS", "COLLARES", "CLUTCH", "CINTURONES", "BRAZALETES"],
    "VESTIDOS LARGOS":  ["AROS", "COLLARES", "CLUTCH", "TOCADOS", "CINTURONES"],
    "VESTIDOS CORTOS":  ["AROS", "CLUTCH", "CINTURONES", "BRAZALETES"],
    "VESTIDOS MIDIS":   ["AROS", "COLLARES", "CLUTCH", "TOCADOS"],
    "NOVIAS LARGOS":    ["TOCADOS", "CLUTCH", "AROS", "BRAZALETES"],
    "NOVIAS CORTOS":    ["TOCADOS", "AROS", "CLUTCH", "BRAZALETES"],
    "FALDAS":           ["TOPS", "AROS", "CINTURONES", "BRAZALETES"],
    "TOPS":             ["FALDAS", "AROS", "COLLARES", "CLUTCH"],
    "BLUSAS":           ["FALDAS", "AROS", "COLLARES", "CLUTCH"],
    "ENTERITOS LARGOS": ["CINTURONES", "AROS", "CLUTCH", "COLLARES"],
    "ENTERITOS CORTOS": ["CINTURONES", "AROS", "CLUTCH", "BRAZALETES"],
}


def resolve_f08b2_complement_types(
    conversation_query: str,
    outfit_product_type: str,
    extract_categories_fn: Callable[[str, Set[str]], List[str]],
    get_concrete_categories_fn: Callable[[], Set[str]],
    types_in_outfit_slot_fn: Callable[[str], List[str]],
) -> List[str]:
    """
    Decision completa de F-08B.2: dada la consulta del usuario y el tipo
    del producto ancla, devuelve la lista final de tipos Shopify concretos
    a recomendar como complemento.

    Args:
        conversation_query: texto de la consulta del usuario.
        outfit_product_type: tipo Shopify del producto ancla (se normaliza
            a mayuscula internamente; el llamador real ya lo hace tambien).
        extract_categories_fn: equivalente a
            improved_fallback_exclude_seen.extract_categories_from_query.
        get_concrete_categories_fn: equivalente a
            improved_fallback_exclude_seen.get_concrete_categories.
        types_in_outfit_slot_fn: equivalente a
            product_taxonomy.types_in_outfit_slot.

    Returns:
        Lista de tipos Shopify concretos (nunca incluye el propio tipo del
        ancla). Puede estar vacia si no hay complemento disponible.
    """
    outfit_product_type = outfit_product_type.upper()
    own_bucket = _B08B2_SHOPIFY_TO_OUTFIT_CAT.get(outfit_product_type, "")

    available_cats = get_concrete_categories_fn()
    detected = extract_categories_fn(conversation_query, available_cats)

    # FIX (20/09/2026): auto-referencia -- la consulta menciona el tipo
    # EXACTO del propio ancla (ej. "esto aros" con ancla AROS); no es un
    # pedido nuevo, es el usuario refiriendose al producto que ya ve.
    detected = [c for c in detected if c.upper() != outfit_product_type]

    query_cats: Optional[List[str]] = None
    if detected:
        distinct = list(dict.fromkeys(c.upper() for c in detected))
        if len(distinct) == 1:
            # FIX (20/09/2026): pedido especifico y unico (ej. "aretes") --
            # usar el tipo concreto tal cual, SIN expandir por bucket.
            query_cats = distinct
        else:
            mapped = {
                _B08B2_SHOPIFY_TO_OUTFIT_CAT[c]
                for c in distinct
                if c in _B08B2_SHOPIFY_TO_OUTFIT_CAT
            }
            # No sugerir el propio bucket del ancla, salvo que sea
            # multi-tipo (accessory/bag).
            if own_bucket not in ("accessory", "bag"):
                mapped.discard(own_bucket)
            if mapped:
                query_cats = list(mapped)

    if query_cats:
        # query_cats puede traer nombres de bucket (minuscula, para expandir
        # via types_in_outfit_slot_fn) o tipos concretos ya especificos
        # (MAYUSCULA, para usar tal cual) -- se distinguen por convencion,
        # sin solapamiento posible entre ambos.
        return [
            t
            for slot in query_cats
            for t in ([slot] if slot.isupper() else types_in_outfit_slot_fn(slot))
            if t != outfit_product_type
        ]

    # Sin categoria explicita utilizable -- comportamiento original sin
    # cambios: mapa de complemento keyed por el tipo del ancla.
    return [
        c for c in _OUTFIT_COMPLEMENT_MAP.get(
            outfit_product_type,
            ["AROS", "COLLARES", "CLUTCH", "CINTURONES"],  # fallback generico
        )
        if c != outfit_product_type
    ]
