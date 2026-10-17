"""
f08_similarity_resolution.py
==============================
Extraido de mcp_conversation_handler.py (bloques F-08 Fase A y F-08C) el
02/10/2026 -- paso 1 del plan acordado en DCT_Cierre_Sesion_01102026.md,
Addendum A, seccion A.4.

Por que existe este modulo:
    F-08 Fase A (similitud visual, Turn 1) y F-08C (similitud visual,
    Turn 2+) implementan EL MISMO pipeline de 5 etapas, duplicado inline en
    dos bloques separados de una funcion async de miles de lineas:

        1. resolver categorias deseadas (texto de la query o expansion a
           categorias "hermanas" del mismo grupo padre)
        2. filtrar el pool FAISS (excluir ancla / vistos, filtrar categoria)
        3. ordenar (particion T8: tipo exacto del ancla primero)
        4. decidir camino: feliz (pool suficiente) / relleno parcial
           restringido / vacio (cae al fallback del llamador)
        5. normalizar (esto ultimo se queda en el llamador:
           normalize_recommendation_dict ya es una funcion compartida)

    Al estar duplicado, los fixes viajaron de forma asimetrica -- confirmado
    leyendo el codigo real el 02/10/2026:
      - C -> A: expansion a hermanas, relleno restringido, particion T8 y
        log de candidate breakdown SI se portaron.
      - A -> C: el intercalado por subtipo (NIVEL 1, 18/07/2026) NUNCA se
        porto a F-08C.
      - C -> A: el aviso category_exhausted_info del camino feliz
        (Caso 3, 26/07/2026) NUNCA se porto a F-08 Fase A.

PASO 1 = SIN CAMBIO DE COMPORTAMIENTO (deliberado):
    Este modulo reproduce EXACTAMENTE lo que hacen hoy ambos bloques,
    INCLUIDAS sus divergencias y el bug conocido de la etiqueta de
    agotamiento (ver build_partial_exhaustion_info). Cada divergencia queda
    codificada como un campo explicito de SimilarityRouteConfig, con dos
    instancias: F08A_ROUTE y F08C_ROUTE. Corregir una divergencia en el
    paso 2 se reduce a cambiar un campo de config + actualizar el test que
    la fija -- no a copiar bloques de codigo entre rutas, que es justamente
    el mecanismo que produjo las asimetrias.

    La equivalencia con el codigo inline original se verifico con un arnes
    de caracterizacion (implementaciones de referencia copiadas literalmente
    del handler, comparadas contra este modulo sobre miles de casos
    aleatorios con los diccionarios reales del repo) -- ver Addendum A del
    DCT, seccion A.6.

    UNICA normalizacion deliberada: la exclusion del producto ancla compara
    str(pid) != str(anchor_pid) en ambas rutas. F-08 Fase A ya usaba str();
    F-08C comparaba pid != anchor_pid sin str(). colbert_client anota los
    tres metodos de busqueda como -> Optional[List[str]], asi que dentro de
    ese contrato ambas formas son identicas; fuera de el (si el embedding
    service devolviera ints), la forma con str() es la unica correcta.

Dependencias:
    Ninguna importada. Todo lo externo llega inyectado como parametro
    (get_parent_categories_fn, type_of) -- mismo criterio que
    f08b2_category_resolution.py y f08b_target_categories.py: modulo
    trivialmente testeable con stubs, sin acoplarlo a como el llamador real
    obtiene sus datos (CATEGORY_KEYWORDS, TF-IDF id_index, etc.).

Contrato de type_of (usado por varias funciones):
    type_of(pid) -> str: el product_type Shopify del producto, o "" si el
    producto no esta en el indice o no tiene tipo. Equivalente en el
    llamador real a:
        lambda pid: tfidf.id_index.get(str(pid), {}).get("product_type", "")


VARIABLES DE ENTORNO -- referencia unica (08/10/2026)
======================================================
Las cuatro son OPCIONALES. Sin ninguna, el sistema funciona con los valores
de la columna "default". Existen como palancas de marcha atras: se cambian en
Cloud Run y aplican SIN redesplegar la imagen, porque se leen en CADA llamada
y no en el default de una firma (que se evaluaria una sola vez, al importar).

  RECS_PRINCIPAL_FIRST   default: activado      (se lee en este modulo)
      G1: ir al catalogo a por mas de LO PEDIDO cuando el pool no trae
      suficiente, en vez de rellenar con hermanas. Ponerlo a 0 revierte G1
      entero: es la palanca de mayor alcance.

  RECS_VISUAL_POOL_BASE  default: faiss_top_k de la ruta   (este modulo)
      Cuantos vecinos pedir de entrada. UNA sola variable para ambas rutas:
      historicamente eran 30 (Fase A) y 50 (F-08C) sin justificacion, y la de
      30 castigaba al turno 1 -- justo donde no hay nada mostrado y el nivel 1
      no puede compensar.

  RECS_VISUAL_POOL_CAP   default: 200           (este modulo)
      Techo del pool despues de sumarle los productos ya mostrados.

  RECS_MAX_ALTERNATIVES  default: 8 (objetivo 6)  (recommendation_set.py)
      Tope de productos "de otra cosa" en la respuesta. 0 los desactiva por
      completo -- palanca de emergencia.
      El objetivo subio de 4 a 6 el 13/10/2026: con los dos bloques separados
      y con titulo en el widget, confundir una alternativa con lo pedido es
      mucho menos probable que en una lista plana.

NO es variable de entorno, aunque el nombre lo sugiera:
  MAX_ALTERNATIVES_TARGET (recommendation_set.py) -- constante que deja
  escrito que el objetivo de producto son 6 alternativas mientras el valor en
  vigor sea 8. Documenta la intencion; no configura nada.

Todas degradan a su default ante un valor ausente, no numerico o fuera de
rango, dejando un logger.warning: un parametro mal configurado nunca debe
tumbar las recomendaciones.
"""
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
import logging as _logging
import os as _os

_log = _logging.getLogger(__name__)

# Alias de tipos, solo para legibilidad de las firmas.
TypeOf = Callable[[str], str]
ParentCategoriesFn = Callable[[], Dict[str, List[str]]]


# =============================================================================
# Configuracion por ruta -- TODAS las divergencias A vs C en un solo lugar
# =============================================================================

@dataclass(frozen=True)
class SimilarityRouteConfig:
    """
    Configuracion de una ruta de similitud visual.

    Cada campo corresponde a una fila de la tabla de divergencias del
    Addendum A (DCT_Cierre_Sesion_01102026.md, seccion A.2). Los valores de
    F08A_ROUTE / F08C_ROUTE reflejan el comportamiento REAL al 02/10/2026,
    no el deseado -- cambiarlos es una decision del paso 2.
    """

    # Nombre corto para logs y telemetria.
    name: str

    # Si True, las categorias detectadas en el TEXTO de la query tienen
    # prioridad sobre la expansion por contexto del ancla.
    # A: False -- F-08 Fase A nunca llama a extract_categories_from_query
    #    (divergencia semantica, pendiente de decision de producto).
    # C: True  -- F-08C la intenta primero.
    use_query_categories: bool

    # Si True, la lista de hermanas resultante se pasa a mayusculas.
    # A: True (s.upper() for s in siblings); C: False (lista tal cual del
    # mapa). Hoy CATEGORY_KEYWORDS ya esta en mayusculas, asi que el efecto
    # practico es nulo -- se conserva por fidelidad, y porque la etiqueta
    # de agotamiento (categories[0]) se envia al LLM tal cual.
    uppercase_sibling_categories: bool

    # Si True, dentro del grupo "hermanas" (todo lo que no es el tipo exacto
    # del ancla) se intercala por subtipo en round-robin (NIVEL 1, 18/07).
    # A: True; C: False -- brecha inversa A->C (paso 2).
    interleave_siblings: bool

    # Etiqueta base de los user_events sinteticos del relleno parcial.
    # El evento extra del ancla usa f"{fill_event_tag}_anchor_boost".
    fill_event_tag: str

    # Valores de `source` / `score_step` para normalize_recommendation_dict
    # (intencionalmente distintos: telemetria por ruta).
    visual_source: str
    visual_score_step: float
    fill_source: str
    fill_score_step: float

    # top_k del pool FAISS. A: 30; C: 50 -- divergencia sin justificacion
    # documentada en el codigo (se conserva tal cual en el paso 1).
    faiss_top_k: int


F08A_ROUTE = SimilarityRouteConfig(
    name="f08a",
    use_query_categories=False,
    uppercase_sibling_categories=True,
    interleave_siblings=True,
    fill_event_tag="f08a_partial_fill",
    visual_source="visual_search_f08",
    visual_score_step=0.03,          # "F-08A usa paso 0.03" (comentario original)
    fill_source="categorized_fill_f08a",
    fill_score_step=0.02,
    faiss_top_k=30,
)

F08C_ROUTE = SimilarityRouteConfig(
    name="f08c",
    use_query_categories=True,
    uppercase_sibling_categories=False,
    interleave_siblings=False,
    fill_event_tag="f08c_partial_fill",
    visual_source="visual_diversification_f08c",
    visual_score_step=0.02,
    fill_source="categorized_fill_f08c",
    fill_score_step=0.02,
    faiss_top_k=50,
)


# =============================================================================
# Tamano del pool visual -- NIVEL 1 del plan E5 (06/10/2026)
# =============================================================================
# PROBLEMA (gap E5, Addendum A.11 / seccion 12.1 de
# SPEC_Contrato_Recomendaciones_06102026.md):
#
# La busqueda pide un numero FIJO de vecinos (30 en Fase A, 50 en F-08C) y
# DESPUES filtra por categoria y descarta lo ya visto. El presupuesto se gasta
# antes de aplicar las restricciones, asi que en sesiones largas casi todo se
# consume en productos que el usuario ya descarto.
#
# Evidencia real (sesion 05/10/2026, ancla "Bolso Indio Aditi"): con 80
# productos ya mostrados, de los 50 vecinos solo sobrevivieron 3 al filtro, y
# ninguno era CARTERAS -- mientras el catalogo SI tenia carteras sin mostrar
# (ni un solo "preferred exhausted" en 1.532 lineas de log). El usuario dejo de
# ver productos que existian.
#
# NIVEL 1: hacer que el presupuesto crezca con lo ya gastado.
#     top_k = faiss_top_k + len(shown_products)
#
# No resuelve la raiz -- para eso hace falta el filtro de categoria DENTRO de
# la busqueda (nivel 2, ver seccion 2.4 de la spec: la ruta de outfit ya lo
# hace con _category_map) -- pero elimina el sintoma en sesiones normales y es
# un cambio de una linea por call site.
#
# COSTE: bajo. IndexFlatIP escanea TODO el indice en cada busqueda sea cual
# sea top_k; este solo afecta a la seleccion del top-k y al tamano del JSON de
# respuesta. Subir de 50 a 130 no multiplica la latencia de busqueda.
#
# TOPE: configurable via RECS_VISUAL_POOL_CAP (default 200). Protege de una
# sesion patologicamente larga y de pedir mas vecinos que productos tiene el
# indice.
_VISUAL_POOL_CAP_DEFAULT = 200


def _read_visual_pool_cap() -> int:
    """
    Lee el tope del pool de RECS_VISUAL_POOL_CAP.

    Degradacion defensiva, mismo criterio que RECS_MAX_ALTERNATIVES en
    recommendation_set.py: un valor ausente, no numerico o no positivo cae al
    default en vez de romper la busqueda visual.
    """
    raw = _os.environ.get("RECS_VISUAL_POOL_CAP")
    if raw is None or str(raw).strip() == "":
        return _VISUAL_POOL_CAP_DEFAULT
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        _log.warning("RECS_VISUAL_POOL_CAP invalido (%r): usando %d",
                     raw, _VISUAL_POOL_CAP_DEFAULT)
        return _VISUAL_POOL_CAP_DEFAULT
    if value <= 0:
        _log.warning("RECS_VISUAL_POOL_CAP no positivo (%d): usando %d",
                     value, _VISUAL_POOL_CAP_DEFAULT)
        return _VISUAL_POOL_CAP_DEFAULT
    return value


def _read_visual_pool_base(route: SimilarityRouteConfig) -> int:
    """
    Base del pool: RECS_VISUAL_POOL_BASE, o el faiss_top_k de la ruta.

    Configurable desde el 07/10/2026. Las dos rutas usaban bases distintas
    (30 en Fase A, 50 en F-08C) sin justificacion documentada -- y la de 30 es
    la del TURNO 1, donde n_shown es siempre 0 y el nivel 1 no puede compensar
    nada. El primer contacto del usuario era el peor servido: evidencia del
    07/10, T1, de 30 vecinos de un clutch solo 3 eran carteras.

    Subirlo es barato. Medido en produccion ese mismo dia: un pool de 154
    tardo 1,8 ms, frente a 1,4-3,5 ms para pools de 58-146. IndexFlatIP
    escanea el indice ENTERO en cada busqueda sea cual sea top_k; este solo
    afecta a la seleccion final y al tamano del JSON. Contrapartida: los
    vecinos extra son menos parecidos por definicion, asi que benefician al
    bloque principal (mejor un bolso menos parecido que ningun bolso) y a las
    alternativas solo les llega lo que sobre.
    """
    raw = _os.environ.get("RECS_VISUAL_POOL_BASE")
    if raw is None or str(raw).strip() == "":
        return route.faiss_top_k
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        _log.warning("RECS_VISUAL_POOL_BASE invalido (%r): usando %d",
                     raw, route.faiss_top_k)
        return route.faiss_top_k
    if value <= 0:
        _log.warning("RECS_VISUAL_POOL_BASE no positivo (%d): usando %d",
                     value, route.faiss_top_k)
        return route.faiss_top_k
    return value


def visual_pool_size(
    route: SimilarityRouteConfig,
    n_shown: int,
    cap: Optional[int] = None,
    base: Optional[int] = None,
) -> int:
    """
    Cuantos vecinos pedir a FAISS, compensando lo ya mostrado.

    Args:
        route: F08A_ROUTE o F08C_ROUTE (aporta el `faiss_top_k` base).
        n_shown: len(shown_products) en este turno.
        cap: tope. None = leer de RECS_VISUAL_POOL_CAP.

    Returns:
        min(route.faiss_top_k + n_shown, cap), nunca por debajo del base.

    Nota sobre Fase A: en Turn 1 `shown_products` siempre esta vacio, asi que
    esta funcion devuelve el base (30) y el comportamiento no cambia. Se cablea
    igualmente por simetria y para no depender de esa invariante.
    """
    if cap is None:
        cap = _read_visual_pool_cap()
    if base is None:
        base = _read_visual_pool_base(route)
    # max(0, ...) protege de un n_shown negativo por un bug aguas arriba.
    wanted = base + max(0, n_shown)
    # El tope nunca debe dejar el pool por debajo del base: si alguien
    # configura un cap absurdamente bajo, degradamos al base en vez de
    # empeorar lo que ya funcionaba.
    return max(base, min(wanted, cap))


# =============================================================================
# G1 -- la decision de ir al catalogo se toma sobre LO PEDIDO, no sobre el total
# =============================================================================
# PROBLEMA (07/10/2026, gap G1). La clasificacion del pool se hacia sobre el
# TOTAL de candidatos:
#
#     classify_pool(len(candidates), n)      # candidates = los 9 tipos hermanos
#
# En el turno T9 del 07/10 habia 11 candidatos: 1 CARTERAS y 10 joyas. Como
# 11 >= 8 el sistema tomo el camino feliz -- "tengo de sobra" -- y NUNCA
# pregunto al catalogo. Pero de lo que el usuario pidio solo tenia UNO.
#
# Dos consecuencias, ambas observadas en produccion ese dia:
#   1. El usuario recibio 1 bolso y 7 joyas, teniendo el catalogo mas bolsos.
#   2. `exhausted` se quedo en False en los 13 turnos, incluso con
#      principal=0, porque solo puede afirmarse tras preguntar al catalogo. El
#      sistema no es que no quisiera avisar: no lo sabia. Y el boton de "ver
#      <categoria> otra vez", cuya condicion es exhausted==True, no habria
#      aparecido nunca.
#
# LA PREGUNTA ESTABA MAL PLANTEADA: no es "tengo n candidatos?", es "tengo n
# de lo que me pidieron?".
#
# Con split_candidates_by_request() el llamador clasifica sobre `own`, va al
# catalogo cuando le faltan del tipo pedido, y las hermanas del pool quedan
# como alternativas. Es el "invertir la prioridad" discutido el 05/10/2026:
# arregla el aviso, habilita el boton de reinicio y mejora el resultado con un
# unico cambio.
#
# Interruptor: RECS_PRINCIPAL_FIRST (default activado). Cambia el camino MAS
# frecuente, asi que debe poder revertirse sin redesplegar la imagen.
_PRINCIPAL_FIRST_DEFAULT = True


def principal_first_enabled() -> bool:
    """Lee RECS_PRINCIPAL_FIRST. Valor no reconocido -> default, con aviso."""
    raw = _os.environ.get("RECS_PRINCIPAL_FIRST")
    if raw is None or str(raw).strip() == "":
        return _PRINCIPAL_FIRST_DEFAULT
    norm = str(raw).strip().lower()
    if norm in ("1", "true", "yes", "on"):
        return True
    if norm in ("0", "false", "no", "off"):
        return False
    _log.warning("RECS_PRINCIPAL_FIRST invalido (%r): usando %s",
                 raw, _PRINCIPAL_FIRST_DEFAULT)
    return _PRINCIPAL_FIRST_DEFAULT


def filter_fill_to_request(
    fill_raw: Sequence[Dict],
    requested_categories: Set[str],
) -> List[Dict]:
    """
    Se queda solo con los productos del catalogo que SON de lo pedido.

    POR QUE HACE FALTA (10/10/2026, evidencia de produccion T10-T11):
    Se llama a smart_fallback con strict_category=True y eventos sinteticos
    de CARTERAS/CLUTCH. Aun asi puede devolver productos de CUALQUIER
    categoria, porque `get_personalized_fallback` tiene un fallthrough propio
    (gap B2): cuando la categoria preferida se queda en CERO productos
    disponibles, se salta strict_category y cae a PRIORIDAD 3 ("diverse"),
    que ignora las categorias por completo.

    Log real del 10/10/2026, turno T10:
        Preferred categories: ['CARTERAS', 'CLUTCH']
        Generated 8 diverse recommendations      <- ni un bolso

    Dos danos concretos:
      1. Entraban productos sin ninguna relacion -- lenceria entre las
         alternativas de un bolso.
      2. El llamador media el agotamiento CONTANDO lo devuelto, asi que 8
         productos equivocados se leian como "el catalogo si tenia" y
         exhausted se quedaba en False. Eso bloquea el aviso al usuario y el
         boton de "ver <categoria> otra vez".

    Este filtro es una defensa LOCAL: no arregla B2, lo contiene en la
    frontera de estas rutas. El arreglo de raiz esta en
    improved_fallback_exclude_seen.py (el `# Continuar con siguiente
    estrategia` de las lineas ~1965 y ~1968) y afecta a TODAS las rutas, por
    lo que se decide y valida aparte.

    Con `requested_categories` vacio devuelve la lista intacta: sin criterio
    de pertenencia no hay nada que filtrar.

    Nota: aqui los items son dicts CRUDOS del catalogo (lo que devuelve
    smart_fallback), no los normalizados -- por eso se lee `product_type` de
    la raiz y no de `product_data`.
    """
    if not requested_categories:
        return list(fill_raw)
    wanted = {c.upper() for c in requested_categories}
    return [
        p for p in fill_raw
        if str((p or {}).get("product_type", "")).upper() in wanted
    ]


def split_candidates_by_request(
    candidates: Sequence[str],
    requested_categories: Set[str],
    type_of: TypeOf,
) -> Tuple[List[str], List[str]]:
    """
    Separa los candidatos del pool en (lo_pedido, el_resto).

    Preserva el orden relativo dentro de cada grupo: no reordena por parecido,
    solo separa -- mismo criterio que RecommendationSet.build().

    Con `requested_categories` vacio devuelve (todos, []): sin criterio de
    pertenencia todo cuenta como pedido. Es el caso INTENT_GENERIC, y evita
    que un ancla sin tipo deje el bloque principal vacio por accidente.
    """
    if not requested_categories:
        return list(candidates), []
    wanted = {c.upper() for c in requested_categories}
    own: List[str] = []
    other: List[str] = []
    for pid in candidates:
        (own if type_of(pid).upper() in wanted else other).append(pid)
    return own, other


# =============================================================================
# Etapa 1 -- resolucion de categorias
# =============================================================================

@dataclass(frozen=True)
class CategoryResolution:
    """
    Resultado de resolve_similarity_categories().

    categories:
        Tipos Shopify a los que se restringe el pool. Lista vacia = sin
        filtro de categoria (solo ocurre si no hay tipo de ancla NI
        categorias en el texto).
    anchor_type_for_ranking:
        Tipo exacto del ancla (mayusculas) a priorizar en la particion T8,
        o None si no aplica (p.ej. el usuario pidio por texto una categoria
        que NO incluye la del ancla -- se respeta su pedido explicito).
    source:
        De donde salieron las categorias, para logs:
        "query_text" | "parent_group" | "exact_type" | "none".
    expansion_error:
        str() de la excepcion si get_parent_categories_fn() fallo (el
        resultado ya viene degradado al tipo exacto); None si no hubo error.
        El llamador decide a que nivel loguearlo (hoy: A debug, C warning).
        str() y no repr(): es exactamente lo que interpolaban los logs
        originales (f"... {_c08_expand_err}"), asi el formato no cambia.
        Comprobar con "is not None" (una excepcion sin mensaje da "").
    """

    categories: List[str]
    anchor_type_for_ranking: Optional[str]
    source: str
    expansion_error: Optional[str] = None


def _find_sibling_group(
    anchor_type_upper: str, parent_map: Dict[str, List[str]]
) -> Optional[List[str]]:
    """
    Devuelve la lista de hermanas del PRIMER grupo padre que contenga el
    tipo, o None.

    ATENCION -- contrato implicito heredado (Addendum A, hallazgo A.3.b):
    AROS/COLLARES/BRAZALETES/BRAZALETE pertenecen a ACCESSORIES y a JOYAS.
    "Primer grupo" significa orden de insercion de CATEGORY_KEYWORDS; hoy
    gana ACCESSORIES solo porque esta definido antes en el archivo. Se
    conserva intacto en el paso 1; hacerlo explicito es tarea del paso 2.
    """
    return next(
        (
            subs
            for subs in parent_map.values()
            if anchor_type_upper in [s.upper() for s in subs]
        ),
        None,
    )


def resolve_similarity_categories(
    route: SimilarityRouteConfig,
    anchor_type: str,
    query_categories: Optional[Sequence[str]],
    get_parent_categories_fn: ParentCategoriesFn,
) -> CategoryResolution:
    """
    Etapa 1: decide a que categorias restringir el pool visual.

    Args:
        route: F08A_ROUTE o F08C_ROUTE.
        anchor_type: product_type del producto que el usuario esta viendo,
            tal cual llega del contexto ("" si no hay). NO se protege contra
            None a proposito: el codigo original haria .upper() sobre None y
            la excepcion la captura el try externo del llamador (fallback a
            TF-IDF / smart_fallback) -- mismo comportamiento aqui.
        query_categories: resultado de extract_categories_from_query() sobre
            la query (o None/[] si no detecto nada). Ignorado si
            route.use_query_categories es False.
        get_parent_categories_fn: equivalente a
            improved_fallback_exclude_seen.get_parent_categories.

    Returns:
        CategoryResolution (ver su docstring).
    """
    if not route.use_query_categories:
        return _resolve_anchor_only(route, anchor_type, get_parent_categories_fn)
    return _resolve_query_first(route, anchor_type, query_categories, get_parent_categories_fn)


def _resolve_anchor_only(
    route: SimilarityRouteConfig,
    anchor_type: str,
    get_parent_categories_fn: ParentCategoriesFn,
) -> CategoryResolution:
    """
    Comportamiento de F-08 Fase A: solo el ancla decide (el texto de la
    query no se consulta nunca). Reproduce el bloque original:

        _f08_type_upper = _f08_ptype.upper()
        _f08_expanded_cats = [_f08_type_upper] if _f08_type_upper else []
        if _f08_type_upper:
            try: ... siblings -> [s.upper() for s in siblings]
            except: [_f08_type_upper]

    La particion T8 de A se aplica siempre que haya tipo de ancla
    (condicion original: "if _f08_type_upper and _f08_tfidf").
    """
    anchor_upper = anchor_type.upper()
    if not anchor_upper:
        return CategoryResolution([], None, "none")

    try:
        siblings = _find_sibling_group(anchor_upper, get_parent_categories_fn())
    except Exception as exc:  # degradacion graceful, igual que el original
        return CategoryResolution([anchor_upper], anchor_upper, "exact_type", str(exc))

    if siblings:
        cats = (
            [s.upper() for s in siblings]
            if route.uppercase_sibling_categories
            else list(siblings)
        )
        return CategoryResolution(cats, anchor_upper, "parent_group")
    return CategoryResolution([anchor_upper], anchor_upper, "exact_type")


def _resolve_query_first(
    route: SimilarityRouteConfig,
    anchor_type: str,
    query_categories: Optional[Sequence[str]],
    get_parent_categories_fn: ParentCategoriesFn,
) -> CategoryResolution:
    """
    Comportamiento de F-08C: el texto de la query manda; el ancla solo se
    usa si el texto no nombra ninguna categoria. Reproduce el bloque
    original:

        if not _c08_query_cats:
            if _c08_ctx_type:
                ranking = ctx.upper()            # se fija ANTES del try
                try: siblings or [ctx]           # [ctx] SIN upper()
                except: [ctx]
        elif ctx and ctx.upper() in [c.upper() for c in query_cats]:
            ranking = ctx.upper()                # FIX 18/07/2026

    Nota de fidelidad: en la rama de contexto, si no hay grupo padre (o la
    expansion falla), la categoria resultante es el tipo del ancla TAL
    CUAL llego (sin .upper()), a diferencia de A. El filtro de la etapa 2
    compara en mayusculas, asi que solo afecta a la etiqueta de agotamiento.
    """
    query_cats = list(query_categories or [])

    if not query_cats:
        if not anchor_type:
            return CategoryResolution([], None, "none")
        anchor_upper = anchor_type.upper()
        try:
            siblings = _find_sibling_group(anchor_upper, get_parent_categories_fn())
        except Exception as exc:
            return CategoryResolution([anchor_type], anchor_upper, "exact_type", str(exc))
        if siblings:
            cats = (
                [s.upper() for s in siblings]
                if route.uppercase_sibling_categories
                else list(siblings)
            )
            return CategoryResolution(cats, anchor_upper, "parent_group")
        return CategoryResolution([anchor_type], anchor_upper, "exact_type")

    # El texto nombro categorias. Solo se protege el tipo del ancla en el
    # ranking si el propio ancla esta incluido en lo pedido (p.ej.
    # "accesorios similares" sobre un Collar). Si el usuario pidio algo que
    # EXCLUYE su tipo ("muestrame bolsos" viendo un Collar), no se prioriza.
    ranking: Optional[str] = None
    if anchor_type and anchor_type.upper() in [c.upper() for c in query_cats]:
        ranking = anchor_type.upper()
    return CategoryResolution(query_cats, ranking, "query_text")


# =============================================================================
# Etapa 2 -- filtrado del pool visual
# =============================================================================

def filter_visual_candidates(
    visual_ids: Iterable[str],
    anchor_pid: str,
    categories: Sequence[str],
    type_of: TypeOf,
    exclude_ids: Set[str],
) -> List[str]:
    """
    Etapa 2: del pool FAISS (ya ordenado por similitud), quita el propio
    ancla, los ya vistos y lo que no pertenece a `categories`. Preserva el
    orden de entrada (= orden de similitud visual).

    Args:
        visual_ids: IDs devueltos por colbert_client (List[str] por contrato).
        anchor_pid: ID del producto ancla.
        categories: salida de resolve_similarity_categories().categories.
            Vacia = sin filtro de categoria.
        type_of: ver contrato en el docstring del modulo.
        exclude_ids: productos ya mostrados (F-08C: shown_products; F-08
            Fase A: set() -- en Turn 1 shown_products siempre esta vacio).

    Comparacion de categoria en mayusculas en ambos lados: A ya recibia sus
    categorias en mayusculas (idempotente); C comparaba exactamente asi.
    """
    cats_upper = [c.upper() for c in categories]
    anchor_str = str(anchor_pid)
    return [
        pid
        for pid in visual_ids
        if pid not in exclude_ids
        and str(pid) != anchor_str  # normalizacion deliberada, ver docstring del modulo
        and (not cats_upper or type_of(pid).upper() in cats_upper)
    ]


def candidate_breakdown(candidates: Iterable[str], type_of: TypeOf) -> Dict[str, int]:
    """
    Conteo de candidatos por tipo (mayusculas), en orden de primera
    aparicion. Alimenta los logs "F-08 / F-08C candidate breakdown"
    (13/07 y 26/07/2026) -- mismo formato exacto en ambas rutas.
    """
    breakdown: Dict[str, int] = {}
    for pid in candidates:
        t = type_of(pid).upper()
        breakdown[t] = breakdown.get(t, 0) + 1
    return breakdown


# =============================================================================
# Etapa 3 -- orden: particion T8 (+ intercalado NIVEL 1 segun ruta)
# =============================================================================

def interleave_by_subtype(pids: Sequence[str], type_of: TypeOf) -> List[str]:
    """
    Round-robin por subtipo (NIVEL 1, 18/07/2026): evita que un hermano
    numeroso (tipicamente AROS, ~524 productos) monopolice el relleno a
    costa de hermanas escasas. Dentro de cada subtipo se preserva el orden
    de similitud; los subtipos se recorren en orden de primera aparicion.

    Ejemplo: [A1, A2, A3, C1, B1] -> [A1, C1, B1, A2, A3]

    Reproduce literalmente _f08_interleave_by_subtype. Unica diferencia de
    forma: la clave de agrupacion para productos sin tipo es "" en vez de
    "UNKNOWN". Es inalcanzable en la practica: esta funcion solo recibe
    candidatos que ya pasaron el filtro de categoria con categorias no
    vacias (la particion requiere tipo de ancla), y un producto sin tipo
    nunca pasa ese filtro.
    """
    by_type: Dict[str, List[str]] = {}
    for pid in pids:
        by_type.setdefault(type_of(pid).upper(), []).append(pid)
    result: List[str] = []
    # Mismo algoritmo exacto que el original: barrido por pasadas, sacando
    # el primero de cada grupo y eliminando los grupos que quedan vacios.
    while any(by_type.values()):
        for key, group in list(by_type.items()):
            if group:
                result.append(group.pop(0))
            if not group:
                del by_type[key]
    return result


def order_candidates(
    route: SimilarityRouteConfig,
    candidates: Sequence[str],
    anchor_type_for_ranking: Optional[str],
    type_of: TypeOf,
) -> List[str]:
    """
    Etapa 3: particion T8 -- tipo EXACTO del ancla primero (preservando su
    orden de similitud), luego el resto. Si route.interleave_siblings, el
    resto se intercala por subtipo; si no, se deja en orden de similitud.

    Sin anchor_type_for_ranking: se devuelve el orden de entrada intacto
    (el usuario pidio por texto algo que no incluye el tipo del ancla).

    Equivalencia con F-08C: su sorted(key=0 si tipo==ancla else 1) es un
    sort estable, es decir exactamente propios + resto en orden original.
    """
    if not anchor_type_for_ranking:
        return list(candidates)
    own = [p for p in candidates if type_of(p).upper() == anchor_type_for_ranking]
    rest = [p for p in candidates if type_of(p).upper() != anchor_type_for_ranking]
    if route.interleave_siblings:
        rest = interleave_by_subtype(rest, type_of)
    return own + rest


# =============================================================================
# Etapa 4 -- decision de camino y senales de agotamiento
# =============================================================================

POOL_HAPPY = "happy"      # >= n: corte directo a n, early-return
POOL_PARTIAL = "partial"  # 1..n-1: visual parcial + relleno restringido
POOL_EMPTY = "empty"      # 0: el llamador cae a su fallback estandar

# -----------------------------------------------------------------------------
# Senal de agotamiento de mcp_context.category_exhausted_info
# -----------------------------------------------------------------------------
# HISTORIA, porque explica por que esto es UNA sola senal y no dos:
#
# Hasta el 04/10/2026 dos situaciones muy distintas escribian el mismo dict
# {category, shown_count, total_count}, y mcp_personalization_engine.py no
# podia distinguirlas: trataba a las dos como agotamiento de catalogo e
# instruia al LLM a decir "ya te mostre TODOS los articulos".
#
# Evidencia (04/10/2026, ancla "Capa de Gasa Champagne"): se reporto 6/8, el
# LLM dijo que eran las ultimas capas disponibles, y en los DOS turnos
# siguientes aparecieron 16 capas mas. Afirmacion falsa al usuario.
#
# El parche de entonces fue anadir un campo `kind` con dos valores:
# "catalog_exhausted" y "result_mixed". Funciono para impedir la MENTIRA,
# pero el 05/10 se confirmo que no bastaba para lograr la REVELACION: el LLM
# seguia sin mencionar la mezcla aunque el prompt se lo pidiera.
#
# Eso se resolvio de raiz con el contrato de recomendaciones: la composicion
# del resultado ya no es una senal que haya que interpretar, sino la propia
# ESTRUCTURA de la respuesta (principal / alternatives). Y con G1 (08/10) el
# camino feliz es homogeneo por construccion, asi que "result_mixed" dejo de
# poder producirse: su unico emisor, detect_happy_path_shortfall(), quedo sin
# llamadas y se elimino el 10/10/2026 junto al campo
# `happy_path_shortfall_signal` y al propio valor "result_mixed".
#
# Queda UNA sola semantica, la unica que siempre estuvo respaldada por datos:
#
#   SIGNAL_CATALOG_EXHAUSTED -- "no encontre mas": se pidieron n productos de
#       la categoria con strict_category=True y el catalogo, descontando lo ya
#       mostrado, no los tenia.
#       La emite build_partial_exhaustion_info. Es tambien la semantica de los
#       call sites que construyen el dict a mano en el handler (smart_fallback
#       "Caso B" y el Caso A de queries de categoria directa), que no llevan
#       la clave y por eso nunca hizo falta tocarlos.
#
# NO reintroducir un segundo valor sin preguntarse antes si la informacion
# cabe en el contrato: ahi es estructura verificable, aqui es una cadena que
# el consumidor tiene que interpretar bien.
SIGNAL_CATALOG_EXHAUSTED = "catalog_exhausted"


def classify_pool(n_candidates: int, n_recommendations: int) -> str:
    """Etapa 4: mismo umbral en ambas rutas (>= n / > 0 / == 0)."""
    if n_candidates >= n_recommendations:
        return POOL_HAPPY
    if n_candidates > 0:
        return POOL_PARTIAL
    return POOL_EMPTY


def build_partial_fill_events(
    route: SimilarityRouteConfig,
    categories: Sequence[str],
    anchor_type_upper: str,
) -> List[Dict[str, object]]:
    """
    user_events sinteticos para smart_fallback(user_query=None,
    strict_category=True): un evento por categoria deseada y un evento
    EXTRA para el tipo exacto del ancla. PRIORIDAD 2 de
    get_personalized_fallback solo usa el top-3 por frecuencia; en grupos
    grandes (ACCESSORIES: 9 tipos) el evento extra garantiza que el tipo
    del ancla nunca quede fuera.

    Args:
        anchor_type_upper: tipo del ancla en MAYUSCULAS (A: _f08_type_upper;
            C: str(ctx product_type).upper()).
    """
    events: List[Dict[str, object]] = []
    for cat in categories:
        events.append({
            "productId": None,
            "product_info": {"product_type": cat, "source": route.fill_event_tag},
            "eventType": "view",
            "source": route.fill_event_tag,
        })
        if cat.upper() == anchor_type_upper:
            events.append({
                "productId": None,
                "product_info": {
                    "product_type": cat,
                    "source": f"{route.fill_event_tag}_anchor_boost",
                },
                "eventType": "view",
                "source": route.fill_event_tag,
            })
    return events


def build_fill_exclusion(
    exclude_ids: Set[str], visual_candidates: Iterable[str], anchor_pid: str
) -> Set[str]:
    """Vistos + candidatos visuales ya usados + el ancla (sin duplicados en el relleno)."""
    return set(exclude_ids) | {str(pid) for pid in visual_candidates} | {anchor_pid}


def build_partial_exhaustion_info(
    categories: Sequence[str],
    n_visual: int,
    n_fill: int,
    n_needed: int,
) -> Optional[Dict[str, object]]:
    """
    Relleno parcial que no alcanzo n (strict_category=True bloqueo el
    broadening): dict para mcp_context.category_exhausted_info, o None.

    !! BUG CONOCIDO, CONSERVADO A PROPOSITO EN EL PASO 1 !!
    La categoria reportada es categories[0] -- el PRIMER HERMANO del grupo
    padre, no el tipo del ancla. Ej.: ancla CAPAS GASA -> se reporta
    "CAPAS BORDADAS"; ancla COLLARES -> "AROS". Afecta a ambas rutas por
    igual. Ver Addendum A, hallazgo A.3.a. La correccion es del paso 2; el
    test test_bug_conocido_etiqueta_es_primer_hermano la fija para que el
    cambio sea una decision visible, no un efecto colateral.

    total_count == shown_count porque con strict_category=True nunca se
    mezclan categorias ajenas (comentario original de F-08C).
    """
    if n_fill >= n_needed:
        return None
    shown = n_visual + n_fill
    return {
        "category": categories[0] if categories else "esta categoria",
        "shown_count": shown,
        "total_count": shown,
        # PASO 2 (04/10/2026): aqui el agotamiento SI esta respaldado -- se
        # pidieron n_needed con strict_category=True y no habia tantos.
        "kind": SIGNAL_CATALOG_EXHAUSTED,
    }


def fill_score_start(last_visual_score: Optional[float]) -> float:
    """
    Score inicial del relleno: un escalon (0.05) por debajo del ultimo
    candidato visual, para preservar el orden visual-primero; 0.90 si no
    hubo ningun candidato visual normalizado.
    """
    if last_visual_score is None:
        return 0.90
    return round(last_visual_score - 0.05, 4)
