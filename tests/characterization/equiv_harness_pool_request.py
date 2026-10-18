"""
Oraculo de equivalencia de build_pool_request() -- E5 nivel 2, paso 2 (17/10/2026).

Uso (desde la raiz del repo):  python tests/characterization/equiv_harness_pool_request.py
No es un test de pytest (nombre sin prefijo test_): es un ORACULO, igual que
equiv_harness_f08.py.

QUE PROTEGE
-----------
El 10/10/2026 las dos rutas de similitud (F-08 Fase A y F-08C) ganaron un
calculo inline de "que se pidio y que puede entrar al pool" (intencion,
familia del ancla, alternativas declaradas). Estaba DUPLICADO, con dos
diferencias de forma:
  - Fase A decidia con `if _f08_type_upper:`.
  - F-08C decidia con `_c08_resolution.source` (y tiene ademas la rama
    "query_text", que Fase A no tiene).
El paso 2 de SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md lo extrae a
f08_similarity_resolution.build_pool_request(). Este oraculo demuestra que la
funcion extraida produce EXACTAMENTE lo mismo que cada copia inline, para las
cinco salidas que el resto del bloque consume: intent, requested_ordered,
requested, alt_types y pool_cats.

POR QUE NO SE AMPLIO equiv_harness_f08.py (desviacion consciente de la spec 8.3)
--------------------------------------------------------------------------------
Ese oraculo es la referencia historica del refactor del 02/10 y su salida
(recuentos por camino) esta citada en el DCT. Anadirle una tercera parte
cambiaria su salida y su tiempo de ejecucion. Un fichero propio deja el del
02/10 intacto y permite ejecutar cada uno por separado.

COMO SE GENERAN LOS CASOS
-------------------------
Igual que el oraculo del 02/10: tipos reales del repo (PRODUCT_TAXONOMY y
ALTERNATIVE_FAMILIES leidos del codigo real), mas casos de estres:
minusculas ("Aros", "capas gasa"), tipo vacio, tipos inexistentes
("TURBANTES"), tipos nupciales, y get_parent_categories_fn real, barajada o
que falla (la expansion falla -> source "exact_type" con expansion_error).
Las funciones de taxonomia que se inyectan son las REALES de product_taxonomy.

AUTO-VERIFICACION (mutation testing incorporado)
------------------------------------------------
Un oraculo que nunca falla puede ser un oraculo ciego (leccion 4 del prompt de
continuidad: `if rset is None: continue` oculto un dia entero de defecto).
Por eso, tras la comparacion principal, el script ejecuta MUTANTES de la
funcion -- versiones con un defecto plausible inyectado -- y exige que cada
uno sea detectado. Si algun mutante sobrevive, el oraculo NO es fiable y el
script termina con error, aunque la comparacion principal haya pasado.
Vive en el repo (no en /tmp) para no repetir la perdida de los oraculos de
mutacion de la sesion anterior.
"""
import ast
import random
import sys

sys.path.insert(0, ".")
from src.recommenders import f08_similarity_resolution as m  # noqa: E402
from src.recommenders import product_taxonomy as tax  # noqa: E402
from src.recommenders.recommendation_set import (  # noqa: E402
    INTENT_CATEGORY_QUERY,
    INTENT_GENERIC,
    INTENT_SIMILARITY,
)

UP = "src/recommenders/"  # ejecutar desde la raiz del repo


def load_literal(path, name):
    """Lee un literal (dict/list) de un .py SIN importarlo.

    improved_fallback_exclude_seen.py arrastra dependencias pesadas al
    importarse; aqui solo hace falta su CATEGORY_KEYWORDS. Mismo mecanismo
    que equiv_harness_f08.py.
    """
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(getattr(t, "id", None) == name for t in targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


CK = load_literal(UP + "improved_fallback_exclude_seen.py", "CATEGORY_KEYWORDS")


def real_get_parent_categories():
    # Copia exacta de improved_fallback_exclude_seen.get_parent_categories()
    # (misma copia que usa equiv_harness_f08.py).
    parents = {}
    for category, config in CK.items():
        if config.get("type") == "parent":
            parents[category] = config.get("subcategories", [])
    return parents


def make_shuffled_parent_fn(rng):
    items = list(real_get_parent_categories().items())
    rng.shuffle(items)
    snapshot = dict(items)
    return lambda: {k: list(v) for k, v in snapshot.items()}


def failing_parent_fn():
    raise RuntimeError("simulated get_parent_categories failure")


# =============================================================================
# REFERENCIA C -- copia LITERAL del bloque inline de F-08C
# (mcp_conversation_handler.py, ~lineas 2051-2085 al 17/10/2026)
# Unicas adaptaciones: entradas como parametros y salidas como dict. Los
# alias _C08_INTENT_* y _c08_* se enlazan a los mismos objetos que importa
# el handler.
# =============================================================================
def ref_c08(_c08_resolution, _c08_ctx_type):
    _C08_INTENT_CATEGORY_QUERY = INTENT_CATEGORY_QUERY
    _C08_INTENT_SIMILARITY = INTENT_SIMILARITY
    _C08_INTENT_GENERIC = INTENT_GENERIC
    _c08_similarity_family = tax.get_similarity_family
    _c08_alternative_types = tax.get_alternative_types
    _c08_query_cats = _c08_resolution.categories  # asi lo asigna el handler

    if _c08_resolution.source == "query_text":
        _c08_intent = _C08_INTENT_CATEGORY_QUERY
        _c08_requested_ordered = list(_c08_query_cats)
    elif _c08_resolution.source in ("parent_group", "exact_type"):
        _c08_intent = _C08_INTENT_SIMILARITY
        _c08_family = _c08_similarity_family(_c08_ctx_type)
        _c08_anchor_up = (_c08_ctx_type or "").upper()
        _c08_requested_ordered = (
            [_c08_anchor_up]
            + [t for t in _c08_family if t != _c08_anchor_up]
        ) if _c08_anchor_up else []
    else:
        _c08_intent = _C08_INTENT_GENERIC
        _c08_requested_ordered = []
    _c08_requested = set(_c08_requested_ordered)

    _c08_alt_types = []
    for _c08_req_t in _c08_requested_ordered:
        for _c08_a in _c08_alternative_types(_c08_req_t):
            if _c08_a not in _c08_alt_types:
                _c08_alt_types.append(_c08_a)
    _c08_pool_cats = list(_c08_requested_ordered) + _c08_alt_types

    return {
        "intent": _c08_intent,
        "requested_ordered": _c08_requested_ordered,
        "requested": _c08_requested,
        "alt_types": _c08_alt_types,
        "pool_cats": _c08_pool_cats,
    }


# =============================================================================
# REFERENCIA A -- copia LITERAL del bloque inline de F-08 Fase A
# (mcp_conversation_handler.py, ~lineas 3005-3028 al 17/10/2026)
# =============================================================================
def ref_f08a(_f08_ptype):
    _F08_INTENT_SIMILARITY = INTENT_SIMILARITY
    _F08_INTENT_GENERIC = INTENT_GENERIC
    _f08_similarity_family = tax.get_similarity_family
    _f08_alternative_types = tax.get_alternative_types
    _f08_type_upper = _f08_ptype.upper()  # asi lo calcula el handler (~2950)

    if _f08_type_upper:
        _f08_intent = _F08_INTENT_SIMILARITY
        _f08_family = _f08_similarity_family(_f08_type_upper)
        _f08_requested_ordered = (
            [_f08_type_upper]
            + [t for t in _f08_family if t != _f08_type_upper]
        )
    else:
        _f08_intent = _F08_INTENT_GENERIC
        _f08_requested_ordered = []
    _f08_requested = set(_f08_requested_ordered)

    _f08_alt_types = []
    for _f08_req_t in _f08_requested_ordered:
        for _f08_a in _f08_alternative_types(_f08_req_t):
            if _f08_a not in _f08_alt_types:
                _f08_alt_types.append(_f08_a)
    _f08_pool_cats = list(_f08_requested_ordered) + _f08_alt_types

    return {
        "intent": _f08_intent,
        "requested_ordered": _f08_requested_ordered,
        "requested": _f08_requested,
        "alt_types": _f08_alt_types,
        "pool_cats": _f08_pool_cats,
    }


# =============================================================================
# CANDIDATA -- como la llamara el handler tras el refactor
# =============================================================================
def mod_pool_request(build_fn, resolution, anchor_type):
    req = build_fn(
        resolution,
        anchor_type,
        similarity_family_fn=tax.get_similarity_family,
        alternative_types_fn=tax.get_alternative_types,
    )
    return {
        "intent": req.intent,
        "requested_ordered": req.requested_ordered,
        "requested": req.requested,
        "alt_types": req.alt_types,
        "pool_cats": req.pool_cats,
    }


def _case_inputs(rng):
    """Genera (anchor_type, query_cats, parent_fn) para un caso."""
    real_types = list(tax.PRODUCT_TAXONOMY.keys())
    alt_keys = list(tax.ALTERNATIVE_FAMILIES.keys())
    anchors = (real_types + alt_keys
               + ["", "Aros", "capas gasa", "TURBANTES", "AROMAS",
                  "novias cortos", "Clutch", "brazalete"])
    cat_names = real_types + ["aros", "Collares", "vestidos largos", "TURBANTES"]

    anchor_type = rng.choice(anchors)
    if rng.random() < 0.5:
        query_cats = []
    else:
        query_cats = rng.sample(cat_names, rng.randint(1, 5))
        if anchor_type and rng.random() < 0.4:
            query_cats.append(anchor_type)  # caso FIX 18/07 (ancla incluida)
    r = rng.random()
    parent_fn = (failing_parent_fn if r < 0.1
                 else make_shuffled_parent_fn(rng) if r < 0.3
                 else real_get_parent_categories)
    return anchor_type, query_cats, parent_fn


def compare(build_fn, n_cases, seed, stop_at_first=False):
    """Compara build_fn con ambas referencias. Devuelve (divergencias, stats)."""
    rng = random.Random(seed)
    diverg = 0
    stats = {}
    for case in range(n_cases):
        anchor_type, query_cats, parent_fn = _case_inputs(rng)

        # --- Ruta A: la resolucion la produce el modulo real (F08A_ROUTE) ---
        res_a = m.resolve_similarity_categories(m.F08A_ROUTE, anchor_type, None, parent_fn)
        ref = ref_f08a(anchor_type)
        got = mod_pool_request(build_fn, res_a, anchor_type)
        key = f"A:{res_a.source}:{ref['intent']}"
        stats[key] = stats.get(key, 0) + 1
        if ref != got:
            diverg += 1
            if stop_at_first:
                return diverg, {"caso": case, "ruta": "A", "anchor": anchor_type,
                                "ref": ref, "got": got}

        # --- Ruta C: con categorias de texto (F08C_ROUTE) ---
        res_c = m.resolve_similarity_categories(m.F08C_ROUTE, anchor_type, query_cats, parent_fn)
        ref = ref_c08(res_c, anchor_type)
        got = mod_pool_request(build_fn, res_c, anchor_type)
        key = f"C:{res_c.source}:{ref['intent']}"
        stats[key] = stats.get(key, 0) + 1
        if ref != got:
            diverg += 1
            if stop_at_first:
                return diverg, {"caso": case, "ruta": "C", "anchor": anchor_type,
                                "query_cats": query_cats, "ref": ref, "got": got}
    return diverg, stats


# =============================================================================
# MUTANTES -- defectos plausibles que el oraculo DEBE detectar
# =============================================================================
# Cada mutante envuelve la funcion real y altera UNA cosa de su salida (o de
# su entrada), imitando un error que alguien podria cometer al tocarla.
def _wrap(transform):
    def build(resolution, anchor_type, *, similarity_family_fn, alternative_types_fn):
        return transform(m.build_pool_request(
            resolution, anchor_type,
            similarity_family_fn=similarity_family_fn,
            alternative_types_fn=alternative_types_fn,
        ))
    return build


def _replace(req, **changes):
    fields = {
        "intent": req.intent,
        "requested_ordered": list(req.requested_ordered),
        "requested": set(req.requested),
        "alt_types": list(req.alt_types),
        "pool_cats": list(req.pool_cats),
    }
    fields.update(changes)
    return m.PoolRequest(**fields)


def _mut_exact_type_only(resolution, anchor_type, *, similarity_family_fn, alternative_types_fn):
    # Volver al tipo EXACTO en vez de la familia (deshace G2, 07/10).
    return m.build_pool_request(resolution, anchor_type,
                                similarity_family_fn=lambda t: [t.upper()] if t else [],
                                alternative_types_fn=alternative_types_fn)


def _mut_alts_of_anchor_only(resolution, anchor_type, *, similarity_family_fn, alternative_types_fn):
    # Pedir alternativas solo del ancla, no de cada miembro de la familia.
    req = m.build_pool_request(resolution, anchor_type,
                               similarity_family_fn=similarity_family_fn,
                               alternative_types_fn=alternative_types_fn)
    first = req.requested_ordered[:1]
    alts = []
    for t in first:
        for a in alternative_types_fn(t):
            if a not in alts:
                alts.append(a)
    return _replace(req, alt_types=alts, pool_cats=list(req.requested_ordered) + alts)


MUTANTS = {
    # Orden: el ancla debe ir PRIMERO (etiqueta de agotamiento, bug A.3.a).
    "familia sin el ancla primero": _wrap(lambda r: _replace(
        r, requested_ordered=sorted(r.requested_ordered),
        pool_cats=sorted(r.requested_ordered) + list(r.alt_types))),
    # Duplicados en alternativas (falta el `not in`).
    "alternativas con duplicados": _wrap(lambda r: _replace(
        r, alt_types=list(r.alt_types) + list(r.alt_types[:1]),
        pool_cats=list(r.pool_cats) + list(r.alt_types[:1]))),
    # pool_cats sin alternativas (vuelta a antes del 10/10).
    "pool sin alternativas": _wrap(lambda r: _replace(
        r, pool_cats=list(r.requested_ordered))),
    # Intencion mal clasificada: query_text tratado como similitud.
    "query_text -> similarity": _wrap(lambda r: _replace(
        r, intent=INTENT_SIMILARITY if r.intent == INTENT_CATEGORY_QUERY else r.intent)),
    # Intencion generica cuando habia ancla.
    "similarity -> generic": _wrap(lambda r: _replace(
        r, intent=INTENT_GENERIC if r.intent == INTENT_SIMILARITY else r.intent)),
    # `requested` desincronizado de requested_ordered.
    "requested vacio": _wrap(lambda r: _replace(r, requested=set())),
    "tipo exacto en vez de familia": _mut_exact_type_only,
    "alternativas solo del ancla": _mut_alts_of_anchor_only,
}


def self_check_mutants(n_cases=3000, seed=17102026):
    """Exige que CADA mutante produzca al menos una divergencia."""
    survivors = []
    for name, mutant in MUTANTS.items():
        diverg, _ = compare(mutant, n_cases, seed, stop_at_first=True)
        status = "detectado" if diverg else "SOBREVIVE"
        print(f"  mutante {name!r}: {status}")
        if not diverg:
            survivors.append(name)
    return survivors


def main(n_cases=20000, seed=20261017):
    diverg, stats = compare(m.build_pool_request, n_cases, seed, stop_at_first=True)
    if diverg:
        print("DIVERGENCIA:", stats)
        sys.exit(1)
    print(f"OK -- {n_cases} casos A + {n_cases} casos C, 0 divergencias")
    print("cobertura (ruta:source:intent):", dict(sorted(stats.items())))

    print("auto-verificacion por mutantes:")
    survivors = self_check_mutants()
    if survivors:
        print(f"ORACULO NO FIABLE -- mutantes supervivientes: {survivors}")
        sys.exit(2)
    print(f"OK -- {len(MUTANTS)}/{len(MUTANTS)} mutantes detectados")


if __name__ == "__main__":
    main()
