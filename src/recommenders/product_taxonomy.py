
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


# =============================================================================
# FAMILIAS DE SIMILITUD (07/10/2026) -- "que cuenta como MAS DE ESTO"
# =============================================================================
# Tercera taxonomia del sistema, con un proposito distinto a las otras dos.
# Conviene no confundirlas:
#
#   CATEGORY_KEYWORDS (improved_fallback_exclude_seen.py)
#       -> que ESCRIBIO el usuario. Deteccion por texto.
#   outfit_slot (arriba, en PRODUCT_TAXONOMY)
#       -> que COMPLETA un conjunto. Responde a "que hueco ocupa".
#   SIMILARITY_FAMILIES (aqui)
#       -> que es LO MISMO que esto. Responde a "mas de esto".
#
# POR QUE HIZO FALTA (evidencia de produccion, 07/10/2026):
# Pidiendo "similares" sobre un clutch, el CLUTCH LEONOR aparecio en 4a
# posicion, por debajo de dos pares de aros. Causa: el contrato definia "lo
# pedido" como el tipo EXACTO del ancla (CARTERAS), y en el catalogo CLUTCH es
# otro product_type -- aunque para quien compra sea el mismo bolso.
#
# Los dos candidatos existentes no servian:
#   - tipo exacto: demasiado estrecho (separa carteras de clutches).
#   - grupo padre de CATEGORY_KEYWORDS: demasiado amplio (ACCESSORIES mete
#     aros, cinturones y tocados en la misma bolsa que los bolsos).
#   - outfit_slot: acierta en `bag` y `top`, pero `dress` mezcla novia con
#     invitada y `accessory` tiene el mismo problema que el grupo padre.
# De ahi un campo propio en vez de reutilizar ninguno.
#
# DOS NIVELES, NO UNO (importante para entender el efecto):
#   Nivel 1 -- que entra en el POOL: lo sigue decidiendo el grupo padre de
#       CATEGORY_KEYWORDS. NO cambia con esto.
#   Nivel 2 -- que cuenta como PRINCIPAL dentro de ese pool: esta tabla.
#   Consecuencia: estrechar una familia NO hace desaparecer a las hermanas --
#   las baja al bloque de alternativas, etiquetadas como tales.
#
# CRITERIO: ante la duda, ESTRECHO. Una familia demasiado amplia reproduce el
# defecto que esto corrige (pedir bolsos y recibir aros). Una estrecha solo
# adelanta el agotamiento del bloque principal -- y desde el fix G1 el
# agotamiento se detecta consultando el catalogo y se comunica al usuario, en
# vez de disimularse.
#
# DEFAULT: un tipo que no aparezca aqui es su propia familia. Anadir un tipo
# nuevo al catalogo nunca lo agrupa con otros por omision.
#
# Decisiones de producto de Yasmani (07/10/2026):
#   - AROS / COLLARES / BRAZALETES: NO son una familia. Viendo unos aros, el
#     usuario no quiere collares.
#   - TOCADOS + ALAS DE NOVIA: SI, accesorios nupcionales de cabeza.
#   - TOPS y BRALETTES: cosas distintas.
#   - PANTALONES y LEGGINGS: no son lo mismo.
#   - Vestidos por largo: SEPARADOS. El largo es una decision, no un matiz --
#     quien mira un vestido largo para una boda de noche no esta a un clic de
#     uno corto. Los otros largos siguen disponibles como alternativas.
SIMILARITY_FAMILIES: Dict[str, List[str]] = {
    # El caso que motivo todo esto: dos product_type, un solo bolso.
    "BOLSOS": ["CARTERAS", "CLUTCH"],

    # PROBLEMA DE DATOS (detectado 07/10/2026): BRAZALETES y BRAZALETE son
    # singular y plural del MISMO producto, registrados como dos tipos
    # distintos. Agruparlos aqui es una tirita; lo correcto seria unificarlos
    # en el catalogo Shopify. Anotado como gap aparte.
    "BRAZALETES": ["BRAZALETES", "BRAZALETE"],

    # Accesorios nupcionales de cabeza. ALAS DE NOVIA estaba en el grupo
    # padre ACCESSORIES junto a aros y cinturones, pese a ser una pieza
    # nupcial muy especifica.
    "TOCADOS_NUPCIALES": ["TOCADOS", "ALAS DE NOVIA"],

    # Ya eran grupo padre en CATEGORY_KEYWORDS; se conserva el criterio.
    "CAPAS": ["CAPAS BORDADAS", "CAPAS GASA"],

    # ENTERITOS y CONJUNTOS estuvieron aqui agrupados hasta el 10/10/2026.
    # Se separaron al detectar una incoherencia con la regla de los vestidos:
    #   - Enteritos: se agrupaban cortos y largos, mientras los vestidos iban
    #     separados por largo. Si "el largo es una decision, no un matiz"
    #     (Yasmani, 07/10), vale igual para un enterito. Separarlos es ademas
    #     lo que permite que la alternativa respete el largo: enterito largo ->
    #     vestido largo, enterito corto -> vestido corto.
    #   - Conjuntos: faldas y pantalones son siluetas distintas, con 41 y 22
    #     productos respectivamente -- volumen de sobra para que cada uno se
    #     sostenga solo. Juntarlos obligaba a una alternativa generica
    #     ("bottoms") que acabaria ofreciendo pantalones a quien mira un
    #     conjunto con falda.
    # Al quedarse con un solo miembro, ya no se declaran: el default de
    # get_similarity_family() (cada tipo, su propia familia) hace el trabajo.

    # Novia SIEMPRE separado de invitada. outfit_slot los mete en el mismo
    # bucket (`conjunto`), que es correcto para completar un outfit pero no
    # para "mas de esto".
    # Estos dos SI siguen juntos: 10 productos en total, sin volumen para
    # sostener dos familias.
    "CONJUNTOS_NOVIA": ["NOVIAS CONJUNTOS FALDAS", "NOVIAS CONJUNTOS PANTALONES"],
}


def get_similarity_family(shopify_type: str) -> List[str]:
    """
    Tipos que cuentan como "lo mismo" al pedir similares a este.

    Devuelve SIEMPRE una lista que incluye al propio tipo. Si no pertenece a
    ninguna familia declarada, devuelve [tipo] -- su propia familia.

    El tipo se normaliza a mayusculas; la lista se devuelve en mayusculas,
    porque el consumidor (el contrato de recomendaciones) compara asi.

    Con tipo vacio o None devuelve [] -- sin ancla no hay criterio de
    pertenencia, y el contrato lo interpreta como "todo cuenta" (generic).
    """
    if not shopify_type:
        return []
    key = shopify_type.upper()
    for members in SIMILARITY_FAMILIES.values():
        upper = [m.upper() for m in members]
        if key in upper:
            return upper
    return [key]


def similarity_family_name(shopify_type: str) -> Optional[str]:
    """Nombre de la familia a la que pertenece el tipo, o None si va solo."""
    if not shopify_type:
        return None
    key = shopify_type.upper()
    for name, members in SIMILARITY_FAMILIES.items():
        if key in [m.upper() for m in members]:
            return name
    return None


# =============================================================================
# FAMILIAS ALTERNATIVAS (10/10/2026) -- "si no queda de esto, que ofrezco"
# =============================================================================
# CUARTA y ultima pieza del reparto de responsabilidades:
#
#   CATEGORY_KEYWORDS    -> que ESCRIBIO el usuario
#   outfit_slot          -> que COMPLETA un conjunto
#   SIMILARITY_FAMILIES  -> que es LO MISMO que esto      (bloque principal)
#   ALTERNATIVE_FAMILIES -> que SUSTITUYE a esto          (bloque alternativas)
#
# POR QUE HIZO FALTA
# ------------------
# Hasta hoy las alternativas salian del GRUPO PADRE de CATEGORY_KEYWORDS, con
# dos consecuencias malas, ambas verificadas el 10/10/2026:
#
#   1. En 17 de los 36 tipos el grupo padre COINCIDE con la familia, asi que
#      el bloque de alternativas era estructuralmente imposible. Entre ellos
#      PANTALONES, KIMONOS, FALDAS, TOPS y ZAPATOS. Cuando esos tipos se
#      agotaban no habia nada que ofrecer y el turno caia al fallback
#      generico: a una consulta de pantalones se respondio con ropa interior
#      reductora, ademas sin stock.
#   2. El grupo padre CRUZA novia e invitada. Verificado: un conjunto de
#      invitada ofrecia los conjuntos de NOVIA como alternativa, violando el
#      invariante que SIMILARITY_FAMILIES si respeta.
#
# POR QUE NO SE USA outfit_slot
# -----------------------------
# Se evaluo y se descarto. Los hermanos de slot son SUSTITUTOS del mismo hueco
# (pantalon/falda/legging), no complementos -- lo que completa un outfit esta
# en OTROS slots, y de eso se encarga F-08B. Como regla general falla en dos
# sitios criticos:
#   - slot `intimates` agrupa REDUCTORES, CALZONES, LENCERIA y PIJAMAS: seria
#     codificar como diseno justo el defecto que se acaba de contener.
#   - slot `enterito` incluye NOVIAS ENTERITOS: cruzaria novia e invitada.
#
# CRITERIO
# --------
# Decisiones de estilismo de Yasmani (10/10/2026). Default: SIN alternativas.
# Un tipo que no aparezca aqui no ofrece nada -- es preferible un bloque vacio
# a una sugerencia que el usuario no entienda.
#
# Los valores se declaran al nivel en que piensa un estilista ("brazaletes") y
# get_alternative_types() expande cada uno a su familia completa, de modo que
# las rarezas del catalogo (BRAZALETE singular) no haya que repetirlas aqui.
ALTERNATIVE_FAMILIES: Dict[str, List[str]] = {
    # -- Joyeria: acotada a joyeria (Yasmani, 10/10) ------------------------
    # Antes, via grupo padre ACCESSORIES, unos aros ofrecian ademas bolsos,
    # cinturones y tocados. Se estrecho a proposito: quien mira unos aros no
    # viene buscando un bolso.
    "AROS": ["COLLARES", "BRAZALETES"],
    "COLLARES": ["AROS", "BRAZALETES"],
    "BRAZALETES": ["AROS", "COLLARES"],
    "BRAZALETE": ["AROS", "COLLARES"],

    # -- Complementos: conservan el alcance que ya tenian --------------------
    # ASIMETRIA DELIBERADA, pendiente de revisar viendo la pantalla: un clutch
    # ofrece aros, pero unos aros ya NO ofrecen clutch. Puede ser legitimo --
    # al componer un look de invitada se salta de bolso a pendiente mas que al
    # reves -- pero conviene confirmarlo con la UI delante.
    "CARTERAS": ["AROS", "COLLARES", "BRAZALETES", "CINTURONES", "TOCADOS"],
    "CLUTCH": ["AROS", "COLLARES", "BRAZALETES", "CINTURONES", "TOCADOS"],
    "CINTURONES": ["CARTERAS", "AROS", "COLLARES", "BRAZALETES", "TOCADOS"],
    "TOCADOS": ["AROS", "COLLARES", "BRAZALETES", "CARTERAS", "CINTURONES"],
    "ALAS DE NOVIA": ["AROS", "COLLARES", "BRAZALETES", "CARTERAS", "CINTURONES"],

    # -- Vestidos y prendas de una pieza ------------------------------------
    # Entre largos de vestido SI hay alternativa: el largo es una decision
    # para el bloque PRINCIPAL, pero un largo distinto es una sugerencia
    # razonable cuando va etiquetada.
    # El cruce a enteritos respeta el largo. VESTIDOS MIDIS no lo lleva
    # porque no existe un enterito midi en el catalogo.
    "VESTIDOS LARGOS": ["VESTIDOS MIDIS", "VESTIDOS CORTOS", "ENTERITOS LARGOS"],
    "VESTIDOS MIDIS": ["VESTIDOS LARGOS", "VESTIDOS CORTOS"],
    "VESTIDOS CORTOS": ["VESTIDOS LARGOS", "VESTIDOS MIDIS", "ENTERITOS CORTOS"],
    "ENTERITOS LARGOS": ["VESTIDOS LARGOS"],
    "ENTERITOS CORTOS": ["VESTIDOS CORTOS"],

    # -- Conjuntos de dos piezas --------------------------------------------
    # "Quien mira un conjunto de dos piezas puede estar considerando
    # componerlo por separado" (Yasmani, 10/10). Cada conjunto apunta a SU
    # pieza inferior, no a un "bottom" generico: por eso se separaron las dos
    # familias (41 y 22 productos, volumen de sobra para sostenerse solas).
    "CONJUNTOS FALDAS": ["FALDAS", "TOPS"],
    "CONJUNTOS PANTALONES": ["PANTALONES", "TOPS"],

    # -- Inferiores ----------------------------------------------------------
    # Nota de inventario (10/10/2026): FALDAS tiene 57 productos y PANTALONES
    # solo 6. La alternativa de un pantalon sera escasa, pero eso es el
    # inventario, no la regla.
    "PANTALONES": ["FALDAS", "LEGGINGS"],
    "FALDAS": ["PANTALONES", "LEGGINGS"],
    "LEGGINGS": ["PANTALONES", "FALDAS"],

    # -- Superiores ----------------------------------------------------------
    # Son tipos distintos para el bloque principal (decision del 07/10), pero
    # si valen como alternativa etiquetada el uno del otro (10/10).
    "TOPS": ["BRALETTES"],
    "BRALETTES": ["TOPS"],

    # -- Abrigo ligero -------------------------------------------------------
    # CAPAS BORDADAS y CAPAS GASA son la misma familia, asi que entre ellas no
    # son alternativa sino principal. Se declara una vez por tipo.
    "CAPAS BORDADAS": ["KIMONOS", "CHAQUETAS"],
    "CAPAS GASA": ["KIMONOS", "CHAQUETAS"],
    "KIMONOS": ["CAPAS BORDADAS", "CHAQUETAS"],
    "CHAQUETAS": ["CAPAS BORDADAS", "KIMONOS"],

    # -- Novia: nunca sale de novia ------------------------------------------
    "NOVIAS LARGOS": ["NOVIAS MIDIS", "NOVIAS CORTOS"],
    "NOVIAS MIDIS": ["NOVIAS LARGOS", "NOVIAS CORTOS"],
    "NOVIAS CORTOS": ["NOVIAS LARGOS", "NOVIAS MIDIS"],
    "NOVIAS ENTERITOS": ["NOVIAS LARGOS", "NOVIAS CORTOS"],
    "NOVIAS CONJUNTOS FALDAS": ["NOVIAS LARGOS", "NOVIAS CORTOS"],
    "NOVIAS CONJUNTOS PANTALONES": ["NOVIAS LARGOS", "NOVIAS CORTOS"],

    # -- SIN alternativas, a proposito ---------------------------------------
    # ZAPATOS: no hay nada comparable en el catalogo.
    # CALZONES, LENCERIA, PIJAMAS, REDUCTORES: ropa interior. Son compras con
    #   intenciones muy distintas entre si (faja, pijama, lenceria), y es la
    #   familia por la que se colo el defecto del 10/10. Dejarlas sin
    #   alternativas es mas seguro que acertar a medias.
    # AROMAS, PACK y cualquier tipo nuevo: default, sin alternativas.
}


# -----------------------------------------------------------------------------
# Tipos NUPCIALES -- frontera que ninguna alternativa puede cruzar
# -----------------------------------------------------------------------------
# La mayoria de tipos de novia se reconocen por el prefijo "NOVIAS", pero NO
# todos: ALAS DE NOVIA es estrictamente nupcial y no lo lleva.
#
# Detectado el 10/10/2026 al revisar el mapa recien escrito: un bolso de
# INVITADA ofrecia ALAS DE NOVIA como alternativa. No estaba declarado asi --
# se colo por la expansion a familia, porque ALAS DE NOVIA comparte la familia
# TOCADOS_NUPCIALES con TOCADOS, y TOCADOS si es una alternativa legitima de
# un bolso.
#
# Por eso la frontera se aplica POR CONSTRUCCION en get_alternative_types() y
# no confiando en que el mapa este bien escrito: cualquier entrada futura, o
# cualquier agrupacion de familia que alguien anada, queda cubierta sin tener
# que acordarse de esta regla.
_BRIDAL_TYPES = frozenset({
    t.upper() for t in PRODUCT_TAXONOMY if t.upper().startswith("NOVIAS")
} | {"ALAS DE NOVIA"})


def is_bridal_type(shopify_type: str) -> bool:
    """True si el tipo es estrictamente nupcial (incluye ALAS DE NOVIA)."""
    return bool(shopify_type) and shopify_type.upper() in _BRIDAL_TYPES


def get_alternative_types(shopify_type: str) -> List[str]:
    """
    Tipos aceptables como ALTERNATIVA cuando no queda de lo pedido.

    Cada entrada declarada se expande a su familia de similitud completa, de
    modo que declarar "BRAZALETES" cubre tambien "BRAZALETE" sin repetirlo.

    Tres filtros, en este orden:
      1. Nunca incluye tipos de la propia familia del ancla: esos son
         `principal`, no alternativa.
      2. Nunca cruza la frontera nupcial, en ningun sentido: un ancla de
         invitada no recibe tipos de novia, y una de novia no recibe de
         invitada. Aplicado por construccion -- ver _BRIDAL_TYPES.
      3. Sin duplicados, preservando el orden declarado (es el de preferencia
         del estilista).

    Devuelve [] para un tipo sin alternativas declaradas, que es el default.
    """
    if not shopify_type:
        return []
    key = shopify_type.upper()
    declarado = None
    for t, alts in ALTERNATIVE_FAMILIES.items():
        if t.upper() == key:
            declarado = alts
            break
    if declarado is None:
        return []

    propia = {m.upper() for m in get_similarity_family(key)}
    ancla_nupcial = is_bridal_type(key)
    salida: List[str] = []
    for alt in declarado:
        for miembro in get_similarity_family(alt):
            if miembro in propia or miembro in salida:
                continue
            if is_bridal_type(miembro) != ancla_nupcial:
                continue
            salida.append(miembro)
    return salida
