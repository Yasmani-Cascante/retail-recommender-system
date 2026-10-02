"""
f08b_target_categories.py
============================
Extraido de mcp_conversation_handler.py (bloque F-08B principal) el
28/09/2026 -- mismo motivo y mismo patron que la extraccion de F-08B.2
(25/09/2026, ver f08b2_category_resolution.py): red de seguridad de tests
automatizados, sin cambiar comportamiento.

Por que existe este modulo:
    La logica de "que categorias de outfit debe buscar F-08B, dado lo que
    el usuario pidio y el tipo del producto ancla" vivia inline, dentro del
    mismo bloque async gigante que hace la llamada HTTP de busqueda visual
    (search_outfit_by_image) y el boost de tipos hermanos (Fase 1b Paso 4)
    -- imposible de testear de forma aislada sin invocar toda esa maquinaria.

    Se extrae aqui SOLO la parte de decision (resolucion de categoria) --
    NO la llamada HTTP, NO el filtrado de resultados por tipo especifico
    (eso necesita el pool de resultados crudo, que no existe hasta despues
    de la llamada), NI el boost de tipos hermanos (Fase 1b Paso 4, con sus
    propias llamadas adicionales al embedding-service). Esas partes quedan
    fuera de alcance de este incremento -- mas riesgosas de extraer por estar
    mezcladas con I/O real. Ver DCT_Cierre_Fase2_Unificacion_Taxonomia_
    27092026.md para el razonamiento de por que se prioriza este incremento
    mas acotado primero.

Diferencia con f08b2_category_resolution.py (el modulo hermano de F-08B.2):
    F-08B principal SI aplica el sistema de conflictos de slot
    (_B08_SLOT_CONFLICTS: dress/enterito/top/bottom/conjunto se excluyen
    mutuamente) -- F-08B.2 (el mecanismo de respaldo, mas simple) nunca lo
    tuvo, solo excluye el propio tipo del ancla. No se unifican en una sola
    funcion porque la logica genuinamente difiere, no por descuido.

Cubre, sin cambiar comportamiento:
    - Auto-referencia (20/09/2026): igual que F-08B.2 -- la consulta
      menciona el tipo exacto del propio ancla, se filtra antes de mapear.
    - Especificidad (21/09/2026): pedido especifico y unico no se expande
      por bucket -- single_specific_type se calcula aqui y se devuelve para
      que el llamador filtre el pool de resultados crudo mas abajo (fuera
      de este modulo, ese pool no existe todavia en este punto).
    - Conflictos de slot (13/07/2026, ampliado 27/09/2026 con "conjunto"):
      dress/enterito/top/bottom/conjunto se excluyen entre si; accessory/bag
      son multi-tipo, nunca se auto-excluyen por completo (permite sugerir
      un COLLAR cuando el ancla es AROS, ambos "accessory").
    - Sugerencias genericas (27/09/2026): usa
      product_taxonomy.generic_suggestion_candidate_slots() en vez de una
      lista propia.
"""
from typing import Callable, List, Optional, Set, Tuple


# Especifico de F-08B (outfit completion) -- NO es taxonomia general, es una
# regla de negocio propia de esta feature. No se mueve a product_taxonomy.py
# porque no se duplica en ningun otro lugar del sistema (a diferencia de los
# diccionarios tipo->outfit_slot que si se unificaron en la Fase 2).
_B08_SLOT_CONFLICTS = {
    "dress":    {"top", "bottom", "enterito", "conjunto"},
    "enterito": {"top", "bottom", "dress", "conjunto"},
    "top":      {"dress", "enterito", "conjunto"},
    "bottom":   {"dress", "enterito", "conjunto"},
    "conjunto": {"dress", "enterito", "top", "bottom"},
}


def resolve_f08b_target_categories(
    conversation_query: str,
    anchor_product_type: str,
    extract_categories_fn: Callable[[str, Set[str]], List[str]],
    get_concrete_categories_fn: Callable[[], Set[str]],
    get_outfit_slot_fn: Callable[[str], Optional[str]],
    generic_suggestion_candidate_slots_fn: Callable[[], List[str]],
) -> Tuple[List[str], Optional[str], bool]:
    """
    Decision de categorias objetivo para F-08B principal.

    Args:
        conversation_query: texto de la consulta del usuario.
        anchor_product_type: tipo Shopify del producto ancla (cualquier
            capitalizacion -- se normaliza internamente).
        extract_categories_fn: equivalente a
            improved_fallback_exclude_seen.extract_categories_from_query.
        get_concrete_categories_fn: equivalente a
            improved_fallback_exclude_seen.get_concrete_categories.
        get_outfit_slot_fn: equivalente a product_taxonomy.get_outfit_slot.
        generic_suggestion_candidate_slots_fn: equivalente a
            product_taxonomy.generic_suggestion_candidate_slots.

    Returns:
        (target_categories, single_specific_type, was_explicit_request):
            target_categories: buckets a pasar como target_categories a
                search_outfit_by_image().
            single_specific_type: tipo Shopify concreto (MAYUSCULA) si el
                pedido fue especifico y unico, o None si fue amplio/generico
                -- el llamador usa esto para filtrar el pool de resultados
                crudo a ese tipo exacto, DESPUES de la llamada de busqueda
                (fuera de este modulo).
            was_explicit_request: True si el usuario menciono una categoria
                explicita en la consulta (especifica o amplia); False si se
                uso el fallback generico. El llamador lo usa para replicar
                el log original "F-08B query category detected" solo cuando
                corresponde.
    """
    anchor_product_type = anchor_product_type.upper()
    own_cat = get_outfit_slot_fn(anchor_product_type) or ""

    excluded_cats = (
        _B08_SLOT_CONFLICTS.get(own_cat, set())
        | (set() if own_cat in ("accessory", "bag") else {own_cat})
    )

    query_target_cats: Optional[List[str]] = None
    single_specific_type: Optional[str] = None
    try:
        available_cats = get_concrete_categories_fn()
        detected = extract_categories_fn(conversation_query, available_cats)
        # FIX (20/09/2026): auto-referencia -- igual que F-08B.2.
        detected = [c for c in detected if c.upper() != anchor_product_type]
        if detected:
            mapped_cats = set()
            for c in detected:
                slot = get_outfit_slot_fn(c.upper())
                if slot:
                    mapped_cats.add(slot)
            # GAP 2 FIX (13/07/2026): resta de conjunto completa (no solo
            # discard(own_cat)) -- una categoria detectada por texto
            # incompatible con el ancla (ej. "top" sobre un vestido) tampoco
            # debe pasar.
            mapped_cats -= excluded_cats
            if mapped_cats:
                query_target_cats = list(mapped_cats)
                # FIX (21/09/2026): pedido especifico y unico -- guardar para
                # que el llamador filtre el pool crudo a ese tipo exacto.
                distinct_detected = list(dict.fromkeys(c.upper() for c in detected))
                if len(distinct_detected) == 1:
                    single_specific_type = distinct_detected[0]
    except Exception:
        # Mismo comportamiento que el bloque original: cualquier fallo en la
        # deteccion por texto cae al comportamiento amplio por defecto, sin
        # propagar el error. El llamador conserva su propio try/except
        # externo para fallos verdaderamente inesperados (ver mcp_
        # conversation_handler.py, "F-08B outfit_completion fallback").
        pass

    was_explicit_request = query_target_cats is not None
    target_cats = query_target_cats if query_target_cats else [
        c for c in generic_suggestion_candidate_slots_fn()
        if c not in excluded_cats
    ]

    return target_cats, single_specific_type, was_explicit_request
