"""
recommendation_set.py
=====================
Contrato de recomendaciones: separa LO PEDIDO de LA ALTERNATIVA.

Especificacion completa:
    docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/
    SPEC_Contrato_Recomendaciones_06102026.md

Por que existe este modulo
--------------------------
Hasta hoy el handler devuelve una LISTA PLANA de n productos que mezcla tres
fuentes con significados incompatibles -- pool visual, catalogo por categoria
y preferencias historicas -- bajo una unica etiqueta "RECOMENDADO PARA TI".
Esa estructura es la causa raiz comun de cinco defectos observados en
produccion (Addendum A.11 del DCT de cierre, gaps E1-E5):

  E1  el usuario no puede saber que esta viendo, y el sistema tampoco puede
      decirselo, porque la estructura de datos no lo contempla
  E2  un item de categoria ajena puede superar en ranking a uno de la
      categoria pedida (05/10/2026: un cinturon por encima de un clutch)
  E3  el "% match" no mide parecido: es la posicion de llenado
  E4  el caso mas frecuente de mezcla no emite ninguna senal, asi que el LLM
      no puede mencionarla
  E5  el filtro de categoria se aplica DESPUES del recorte top_k

PRINCIPIO RECTOR
----------------
    Cada producto lleva su procedencia, y el orden nunca cruza bloques.

Lo segundo es lo que elimina E2 POR CONSTRUCCION: `principal` y
`alternatives` son listas distintas y el aplanado las concatena en ese orden,
asi que ningun reordenamiento posterior puede colar una alternativa por
encima de lo pedido -- siempre que el reordenamiento se aplique por bloque
(ver reorder_within_blocks).

`principal` se define por la INTENCION, no por la categoria
-----------------------------------------------------------
Decision de producto (Yasmani, 06/10/2026). En similitud la intencion es
"mas de esto"; en completar outfit es "lo que combina". Por eso el contrato
no sabe que es "lo pedido": se lo dice la ruta via RequestSpec. Asi las
cuatro rutas usan la misma funcion de particion, sin casos especiales --
incluido outfit, donde mezclar categorias ES lo correcto.

Dependencias
------------
Ninguna importada. Todo lo externo llega inyectado (type_of, collections_of),
mismo criterio que f08_similarity_resolution.py: modulo trivialmente testeable
con stubs y sin acoplar a como el llamador obtiene sus datos.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set
import logging
import os

log = logging.getLogger(__name__)

# -- Alias de tipos, solo para legibilidad de las firmas --------------------
TypeOf = Callable[[Dict], str]              # item -> product_type ("" si no hay)
CollectionsOf = Callable[[Dict], Set[str]]  # item -> colecciones en minusculas


# =============================================================================
# Intenciones
# =============================================================================
# Cada intencion define que cuenta como "lo pedido". Es lo unico que la ruta
# tiene que decidir; el resto del contrato es identico para las cuatro.

INTENT_SIMILARITY = "similarity"                  # "mas de esto" (F-08 Fase A, F-08C)
INTENT_OUTFIT_COMPLEMENT = "outfit_complement"    # "lo que combina" (F-08B, F-08B.2)
INTENT_CATEGORY_QUERY = "category_query"          # "muestrame bolsos"
INTENT_GENERIC = "generic"                        # sin intencion clara: todo es principal

VALID_INTENTS = frozenset({
    INTENT_SIMILARITY,
    INTENT_OUTFIT_COMPLEMENT,
    INTENT_CATEGORY_QUERY,
    INTENT_GENERIC,
})

# Procedencia de cada item. Va POR ITEM, no por bloque: `principal` puede
# mezclar procedencias de forma legitima (bolsos del pool visual + bolsos
# traidos del catalogo). Todos son bolsos, pero solo los primeros tienen
# vecindad visual medida -- y por tanto solo ellos pueden mostrar un
# porcentaje de parecido honesto.
ORIGIN_VISUAL = "visual"          # vino del pool FAISS
ORIGIN_CATALOG = "catalog"        # vino del catalogo por categoria
ORIGIN_BEHAVIORAL = "behavioral"  # vino de preferencias historicas

# -----------------------------------------------------------------------------
# Tope de alternativas -- CONFIGURABLE
# -----------------------------------------------------------------------------
# Regla acordada (Yasmani, 06/10/2026):
#     max_alternativas = min(n_requested - len(principal), MAX_ALTERNATIVES)
#
# OBJETIVO: 6 (Yasmani, 13/10/2026). Antes era 4.
# El razonamiento original: con n=8, mas de 4 alternativas significa que la
# mayoria de lo que ve el usuario NO es lo que pidio.
# Lo que cambio: con los dos bloques SEPARADOS y con titulo en el widget
# (fase 3), el riesgo de confundir una alternativa con lo pedido baja mucho,
# porque el usuario ve a que grupo pertenece cada tarjeta. En una lista plana
# e indistinguible, 4 era prudente; con bloques etiquetados se quedaba corto.
#
# VALOR DE DESPLIEGUE ACTUAL: 8 (temporal, decision de Yasmani 06/10/2026).
# Con 8 el tope nunca muerde (min(8 - len(principal), 8) == 8 - len(principal)),
# asi que el numero TOTAL de productos devueltos es identico al de hoy. Esto
# permite desplegar la fase 1 del contrato -- que si cambia el ORDEN, eliminando
# el ranking invertido E2 -- sin cambiar a la vez cuantos productos se
# devuelven. Un cambio observable a la vez.
#
# COMO BAJARLO AL OBJETIVO: poner RECS_MAX_ALTERNATIVES=6 en la variable de
# entorno de Cloud Run (sin redeploy de imagen), o cambiar el default de abajo.
# No hace falta tocar ninguna ruta: build() lo lee de aqui.

MAX_ALTERNATIVES_TARGET = 6   # objetivo de producto, no el valor en vigor
_MAX_ALTERNATIVES_ROLLOUT = 8  # valor temporal de despliegue


def _read_max_alternatives() -> int:
    """
    Lee el tope de la variable de entorno RECS_MAX_ALTERNATIVES.

    Degradacion defensiva: un valor ausente, no numerico o negativo cae al
    valor de despliegue en vez de romper el arranque. Un tope mal configurado
    nunca debe tumbar las recomendaciones.
    """
    raw = os.environ.get("RECS_MAX_ALTERNATIVES")
    if raw is None or str(raw).strip() == "":
        return _MAX_ALTERNATIVES_ROLLOUT
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        log.warning(
            "RECS_MAX_ALTERNATIVES invalido (%r): usando %d",
            raw, _MAX_ALTERNATIVES_ROLLOUT,
        )
        return _MAX_ALTERNATIVES_ROLLOUT
    if value < 0:
        log.warning(
            "RECS_MAX_ALTERNATIVES negativo (%d): usando %d",
            value, _MAX_ALTERNATIVES_ROLLOUT,
        )
        return _MAX_ALTERNATIVES_ROLLOUT
    return value


MAX_ALTERNATIVES = _read_max_alternatives()


# =============================================================================
# RequestSpec -- que cuenta como "lo pedido"
# =============================================================================

@dataclass(frozen=True)
class RequestSpec:
    """
    Criterio de pertenencia al bloque principal.

    categories:
        Tipos de producto que cuentan como principal. Conjunto VACIO =
        "todo cuenta" (intencion generic), no "nada cuenta".

    attributes:
        Restricciones duras adicionales sobre `product_data`, p.ej.
        {"color": "verde"}. VACIO hoy en las cuatro rutas.

        Existe desde el dia uno a proposito: la busqueda por atributos
        (BACKLOG_Busqueda_por_Atributos_Color_24072026.md) se expresa en
        este contrato sin ninguna pieza nueva --
            "vestidos similares pero verdes"
            -> principal:    vestidos similares que SON verdes de verdad
            -> alternatives: vestidos similares de otros colores
        Cuando llegue el color solo hay que rellenar este campo: ni una rama
        nueva ni un caso especial. Mientras este vacio el comportamiento es
        identico al de una particion solo por categoria.

        Ojo: la validacion contra el dato real del catalogo es precisamente
        la "red de seguridad" de la seccion 3.3 de ese backlog -- el empujon
        del composite embedding no garantiza nada por si solo.
    """

    categories: Set[str] = field(default_factory=set)
    attributes: Dict[str, str] = field(default_factory=dict)


def belongs_to_principal(
    item: Dict,
    request: RequestSpec,
    type_of: TypeOf,
) -> bool:
    """
    Predicado de pertenencia al bloque principal.

    Con `request.categories` vacio y `request.attributes` vacio devuelve
    siempre True -- es el caso INTENT_GENERIC, donde todo es principal.

    La comparacion de categoria es insensible a mayusculas en ambos lados,
    igual que el resto del sistema (CATEGORY_KEYWORDS y product_type de
    Shopify no estan normalizados de forma consistente).
    """
    if request.categories:
        wanted = {c.upper() for c in request.categories}
        if type_of(item).upper() not in wanted:
            return False

    # Restricciones duras adicionales. Se leen de product_data (el dict crudo
    # del catalogo que normalize_recommendation_dict anida en cada item).
    for attr, expected in request.attributes.items():
        actual = (item.get("product_data") or {}).get(attr, "")
        if str(actual).strip().lower() != str(expected).strip().lower():
            return False

    return True


# =============================================================================
# Bloques
# =============================================================================

@dataclass(frozen=True)
class Block:
    """
    Un bloque de recomendaciones con significado homogeneo.

    categories:
        Tipos que el bloque contiene DE HECHO, en orden de primera aparicion.
        No es lo mismo que RequestSpec.categories (lo pedido): si se pidieron
        CARTERAS y solo habia 2, aqui aparece ["CARTERAS"] y no el resto.

    exhausted:
        Solo significativo en `principal`. True SOLO si se consulto al
        catalogo por esa categoria y no habia mas productos tras las
        exclusiones. False si `principal` quedo corto porque se agoto el
        POOL VISUAL aunque el catalogo tenga mas.

        Esta distincion es exactamente la que faltaba el 04/10/2026, cuando
        una senal sobrecargada hizo que el LLM afirmara "son las ultimas
        capas disponibles" y en los dos turnos siguientes aparecieran 16 mas.
        Aqui es un booleano con un unico significado, no un campo
        reinterpretable.

        Gobierna ademas la aparicion del boton "ver <categoria> otra vez" en
        UI: solo tiene sentido ofrecer reiniciar el catalogo si el catalogo
        esta realmente agotado.
    """

    items: List[Dict] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    exhausted: bool = False

    def __len__(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class Meta:
    """Contexto de la peticion, para logs, telemetria y depuracion."""

    anchor_id: Optional[str] = None
    anchor_type: Optional[str] = None
    request: RequestSpec = field(default_factory=RequestSpec)
    n_requested: int = 0
    route: str = "unknown"   # f08a | f08c | f08b | smart_fallback | standard


def _distinct_types(items: Iterable[Dict], type_of: TypeOf) -> List[str]:
    """Tipos presentes, en orden de primera aparicion, sin duplicados."""
    seen: List[str] = []
    for it in items:
        t = type_of(it).upper()
        if t and t not in seen:
            seen.append(t)
    return seen


# =============================================================================
# RecommendationSet
# =============================================================================

@dataclass(frozen=True)
class RecommendationSet:
    """
    Resultado completo de una peticion de recomendaciones.

    Se construye con RecommendationSet.build(); no instanciar a mano salvo en
    tests, porque build() es quien aplica la particion, el tope y el orden.
    """

    intent: str
    principal: Block
    alternatives: Block
    meta: Meta

    # -- Construccion -------------------------------------------------------
    @classmethod
    def build(
        cls,
        intent: str,
        items: Sequence[Dict],
        request: RequestSpec,
        n_requested: int,
        type_of: TypeOf,
        *,
        anchor_id: Optional[str] = None,
        anchor_type: Optional[str] = None,
        route: str = "unknown",
        exhausted: bool = False,
        max_alternatives: int = -1,
    ) -> "RecommendationSet":
        """
        Reparte `items` en los dos bloques y aplica el tope de alternativas.

        Args:
            intent: una de VALID_INTENTS.
            items: productos YA normalizados (esquema de
                normalize_recommendation_dict), en el orden en que la ruta
                quiere mostrarlos DENTRO de su grupo. build() NO reordena por
                parecido: solo separa. El orden relativo dentro de cada
                bloque se preserva tal cual llego.
            request: criterio de pertenencia al principal.
            n_requested: cuantos productos se pidieron (tipicamente 8).
            type_of: item -> product_type.
            exhausted: ver Block.exhausted. Lo sabe solo la ruta, porque
                depende de si se consulto al catalogo y que respondio.
            max_alternatives: tope duro. Default MAX_ALTERNATIVES, que se lee
                de la variable de entorno RECS_MAX_ALTERNATIVES (ver arriba).
                Pasarlo explicito es para tests; en produccion se deja el
                default para poder ajustarlo sin tocar las rutas.

        Returns:
            RecommendationSet con los dos bloques ya recortados.

        Regla de tope (decision de Yasmani, 06/10/2026):
            max = min(n_requested - len(principal), max_alternatives)

        Con max_alternatives=6 (OBJETIVO desde el 13/10/2026):
            principal=6 -> alternativas 2 -> total 8
            principal=4 -> alternativas 4 -> total 8
            principal=2 -> alternativas 6 -> total 8
            principal=0 -> alternativas 6 (no 8) -> total 6

        Con max_alternatives=8 (DESPLIEGUE ACTUAL) el tope nunca muerde y el
        total siempre llega a n_requested si hay material -- mismo numero de
        productos que hoy, pero ya con el orden correcto.

        `principal` PUEDE quedarse vacio (decision de Yasmani): es honesto, y
        el widget decide si dibuja el bloque.
        """
        if intent not in VALID_INTENTS:
            raise ValueError(f"intent desconocido: {intent!r} (validos: {sorted(VALID_INTENTS)})")

        # -1 = "usa el valor configurado". Se resuelve AQUI y no en la firma
        # para que un cambio de RECS_MAX_ALTERNATIVES en caliente aplique sin
        # reimportar el modulo (los defaults de firma se evaluan una sola vez,
        # al importar).
        if max_alternatives < 0:
            max_alternatives = _read_max_alternatives()

        principal_items: List[Dict] = []
        alternative_items: List[Dict] = []
        for it in items:
            if belongs_to_principal(it, request, type_of):
                principal_items.append(it)
            else:
                alternative_items.append(it)

        # El principal se recorta a lo pedido; las alternativas al hueco que
        # queda, nunca por encima del tope duro. max(0, ...) protege el caso
        # en que la ruta entregue mas principales que n_requested.
        principal_items = principal_items[:n_requested]
        room = max(0, n_requested - len(principal_items))
        alternative_items = alternative_items[:min(room, max_alternatives)]

        return cls(
            intent=intent,
            principal=Block(
                items=principal_items,
                categories=_distinct_types(principal_items, type_of),
                exhausted=exhausted,
            ),
            alternatives=Block(
                items=alternative_items,
                categories=_distinct_types(alternative_items, type_of),
                exhausted=False,   # no aplica: ver Block.exhausted
            ),
            meta=Meta(
                anchor_id=anchor_id,
                anchor_type=anchor_type,
                request=request,
                n_requested=n_requested,
                route=route,
            ),
        )

    # -- Salidas ------------------------------------------------------------
    def to_flat_list(self) -> List[Dict]:
        """
        Aplana a la lista que esperan los consumidores actuales.

        ESTA ES LA LINEA QUE ELIMINA E2. El orden nunca cruza bloques: una
        alternativa no puede aparecer por encima de un principal, pase lo que
        pase aguas arriba. No es una regla de ordenacion que alguien pueda
        saltarse -- son listas distintas concatenadas.

        Mismo tipo y mismo esquema por item que antes (mas los campos
        `origin` y `visual_rank`), asi que ningun consumidor se rompe: los
        campos extra se ignoran.
        """
        return list(self.principal.items) + list(self.alternatives.items)

    def to_prompt_facts(self) -> Dict:
        """
        Hechos para el redactor (mcp_personalization_engine), NO instrucciones.

        El 04/10/2026 se arreglo que el LLM afirmara en falso el agotamiento
        anadiendo una prohibicion al prompt. Funciono. Pero el 05/10 se
        confirmo que pedirle que REVELE la mezcla no funciona: en el unico
        turno donde la senal se emitio, el LLM tampoco la menciono, pese a
        pedirselo explicitamente. Una instruccion entre muchas es opcional.

        Entregarle dos bloques con nombre y sus cuentas es distinto:
        mencionar lo que uno tiene delante es lo natural. Por eso la
        revelacion se resuelve con estructura y no con prompt.
        """
        return {
            "intent": self.intent,
            "principal_count": len(self.principal),
            "principal_categories": list(self.principal.categories),
            "alternatives_count": len(self.alternatives),
            "alternatives_categories": list(self.alternatives.categories),
            "catalog_exhausted": self.principal.exhausted,
            "requested_category": (
                sorted(self.meta.request.categories)[0]
                if self.meta.request.categories else None
            ),
        }

    def to_api_dict(self) -> Dict:
        """
        Forma serializable para la API (fase 3.1), junto a la lista plana.

        LLEVA IDENTIFICADORES, NO PRODUCTOS (13/10/2026). La respuesta sigue
        teniendo UNA sola fuente de productos: el campo `recommendations`, que
        ya viene ordenado principal-y-luego-alternativas por to_flat_list().
        Aqui solo viaja COMO agruparlos.

        Dos razones para no duplicar los items:
          - Tamano: cada producto lleva imagen, descripcion y precio; mandarlos
            dos veces duplica el payload del turno.
          - Y la de peso: dos copias son dos fuentes de verdad. Si alguien
            filtra o reordena una y no la otra, divergen en silencio. Con ids,
            una sola lista manda y los bloques solo la particionan.

        El consumidor agrupa por id. Si un id del bloque no aparece en
        `recommendations` (no deberia pasar), lo correcto es ignorarlo, no
        inventar una tarjeta.
        """
        return {
            "intent": self.intent,
            "principal": {
                "product_ids": [str(i.get("id")) for i in self.principal.items],
                "categories": list(self.principal.categories),
                # Condicion del boton "ver <categoria> otra vez" en la UI:
                # True SOLO si se consulto al catalogo y no habia mas.
                "exhausted": self.principal.exhausted,
            },
            "alternatives": {
                "product_ids": [str(i.get("id")) for i in self.alternatives.items],
                "categories": list(self.alternatives.categories),
            },
            "meta": {
                "anchor_id": self.meta.anchor_id,
                "anchor_type": self.meta.anchor_type,
                "n_requested": self.meta.n_requested,
                "route": self.meta.route,
                "requested_categories": sorted(self.meta.request.categories),
                "requested_attributes": dict(self.meta.request.attributes),
            },
        }


# =============================================================================
# Procedencia y parecido por item
# =============================================================================

def tag_origin(
    item: Dict,
    origin: str,
    visual_rank: Optional[int] = None,
    visual_score: Optional[float] = None,
) -> Dict:
    """
    Devuelve una COPIA del item con su procedencia y su parecido real.

    visual_score:
        Similitud coseno real devuelta por FAISS. Hoy llega None porque el
        embedding-service la calcula y la descarta en origen:
            _, indices = self._faiss_index.search(vec, top_k + 1)
        Ese guion bajo tira las distancias, que con IndexFlatIP y vectores
        normalizados SON la similitud coseno. Recuperarla es un cambio
        pequeno en tres sitios (servicio, colbert_client, aqui) -- ver
        seccion 2.3 de la spec.

    visual_rank:
        Posicion 0-indexed en el pool FAISS. Es el respaldo ordinal mientras
        se propaga lo anterior, y un dato util en si mismo.

    Para items que no vienen del pool visual ambos quedan a None: NO hay
    parecido medido, y fingirlo es exactamente el defecto E3. El widget solo
    debe mostrar porcentaje donde visual_score no es None.
    """
    if origin not in (ORIGIN_VISUAL, ORIGIN_CATALOG, ORIGIN_BEHAVIORAL):
        raise ValueError(f"origin desconocido: {origin!r}")
    out = dict(item)
    out["origin"] = origin
    out["visual_rank"] = visual_rank
    out["visual_score"] = visual_score
    return out


# =============================================================================
# Reordenamiento por coleccion -- DENTRO de cada bloque
# =============================================================================

def reorder_by_collection(
    items: Sequence[Dict],
    current_collections: Set[str],
    collections_of: CollectionsOf,
) -> List[Dict]:
    """
    Sube los items que comparten coleccion con el producto que el usuario
    esta viendo, PRESERVANDO el orden relativo dentro de cada grupo.

    Reemplaza al mecanismo actual del handler (COLLECTION_BOOST = 0.15 sumado
    a similarity_score + sorted global). Dos razones para cambiarlo:

      1. El sorted GLOBAL romperia los bloques en cuanto exista el contrato:
         podria subir una alternativa por encima de un principal. Hoy no se
         nota solo porque las rutas visuales retornan antes de llegar ahi --
         es una bomba de relojeria, no un gap aparte.
      2. Sumar un boost a similarity_score corrompe el campo de parecido.
         Cuando el score sea la similitud coseno real (2.3 de la spec),
         sumarle 0.15 lo convertiria otra vez en un numero inventado.

    Particion estable en vez de sort por score: mismo efecto de "primero los
    de la coleccion", sin tocar ninguna puntuacion.
    """
    if not current_collections or not items:
        return list(items)
    same, rest = [], []
    for it in items:
        (same if (collections_of(it) & current_collections) else rest).append(it)
    return same + rest


def reorder_within_blocks(
    rset: RecommendationSet,
    current_collections: Set[str],
    collections_of: CollectionsOf,
) -> RecommendationSet:
    """
    Aplica reorder_by_collection a cada bloque POR SEPARADO.

    Un producto de la misma coleccion sube dentro de su bloque, nunca lo
    atraviesa. Es la pieza que mantiene la garantia de to_flat_list().
    """
    from dataclasses import replace
    return replace(
        rset,
        principal=replace(
            rset.principal,
            items=reorder_by_collection(rset.principal.items, current_collections, collections_of),
        ),
        alternatives=replace(
            rset.alternatives,
            items=reorder_by_collection(rset.alternatives.items, current_collections, collections_of),
        ),
    )
