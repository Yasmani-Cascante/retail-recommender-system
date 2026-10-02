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

    Se extrajo el 25/09/2026 SIN CAMBIAR EL COMPORTAMIENTO, para poder
    escribir tests automatizados reales antes de la refactorizacion mayor
    de unificacion de taxonomia (roadmap Fase 2, item 4).

ACTUALIZADO (26/09/2026) -- decision de unificacion de taxonomia CERRADA:
    _B08B2_SHOPIFY_TO_OUTFIT_CAT y _OUTFIT_COMPLEMENT_MAP quedaron
    RETIRADOS de este modulo (ver DCT_Fase1b_Composite_Embedding_F08B_
    Cierre_24072026.md, Addendum 6, y taxonomy_centroid_audit.py corrido
    contra el catalogo real, 26/09/2026):
      - _B08B2_SHOPIFY_TO_OUTFIT_CAT: donde coincidia con product_taxonomy.py
        coincidia sin excepcion (confirmado por el script de auditoria);
        donde no, product_taxonomy.py ya era mas completo (8 gaps contra 14
        -- entre ellos, las 6 variantes de NOVIAS, 241 productos, ausentes
        SOLO de la copia que vivia aqui).
      - _OUTFIT_COMPLEMENT_MAP: 19 de 29 tipos de prenda reales ya caian a
        su fallback generico de 4 items -- en la practica era una version
        incompleta de "todo el bucket accessory+bag", que es exactamente lo
        que types_in_outfit_slot_fn ya resuelve, probado y en produccion
        desde hace semanas para pedidos amplios ("accesorios").

    Esta funcion ahora recibe get_outfit_slot_fn ademas de
    types_in_outfit_slot_fn (ambas equivalentes a funciones de
    product_taxonomy.py) -- ya no mantiene ninguna copia propia de
    taxonomia. Las dependencias siguen inyectadas como parametros (no
    importadas directamente) para mantener este modulo trivialmente
    testeable con stubs simples, sin acoplarlo a la forma exacta en que el
    llamador real las obtiene.

Cubre los dos bugs reales encontrados y corregidos la semana del
20-21/09/2026:
    1. Auto-referencia: la consulta menciona el tipo exacto del propio ancla
       ("esto aros" con ancla AROS) -- se filtra antes de mapear, no se trata
       como un pedido nuevo.
    2. Sobre-expansion: una categoria concreta unica y especifica ("aretes")
       se mapeaba a su bucket completo (todo "accessory") en vez de respetar
       la especificidad del pedido -- se usa el tipo exacto sin expandir.
    3. Sin categoria explicita utilizable: desde el 26/09/2026, devuelve
       TODO el bucket accessory+bag (menos el propio tipo del ancla) -- el
       mismo mecanismo ya validado para pedidos amplios como "accesorios",
       en vez del retirado _OUTFIT_COMPLEMENT_MAP (que nunca cubrio anclas
       de tipo accesorio y tenia 19 de 29 tipos de prenda sin entrada
       propia de todas formas).
"""
from typing import Callable, List, Optional, Set


def resolve_f08b2_complement_types(
    conversation_query: str,
    outfit_product_type: str,
    extract_categories_fn: Callable[[str, Set[str]], List[str]],
    get_concrete_categories_fn: Callable[[], Set[str]],
    get_outfit_slot_fn: Callable[[str], Optional[str]],
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
        get_outfit_slot_fn: equivalente a product_taxonomy.get_outfit_slot.
        types_in_outfit_slot_fn: equivalente a
            product_taxonomy.types_in_outfit_slot.

    Returns:
        Lista de tipos Shopify concretos (nunca incluye el propio tipo del
        ancla). Puede estar vacia si no hay complemento disponible.
    """
    outfit_product_type = outfit_product_type.upper()
    own_bucket = get_outfit_slot_fn(outfit_product_type) or ""

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
            mapped = set()
            for c in distinct:
                slot = get_outfit_slot_fn(c)
                if slot:
                    mapped.add(slot)
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

    # FIX (26/09/2026): sin categoria explicita utilizable -- antes caia al
    # retirado _OUTFIT_COMPLEMENT_MAP. Ahora usa el mismo mecanismo ya
    # validado para pedidos amplios: todo el bucket accessory+bag, menos el
    # propio tipo del ancla.
    return [
        t
        for slot in ("accessory", "bag")
        for t in types_in_outfit_slot_fn(slot)
        if t != outfit_product_type
    ]
