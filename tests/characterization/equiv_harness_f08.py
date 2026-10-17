"""
Arnes de caracterizacion F-08 Fase A / F-08C (02/10/2026).

Uso (desde la raiz del repo):  python tests/characterization/equiv_harness_f08.py
No es un test de pytest (nombre sin prefijo test_): es el ORACULO del paso 1.
Tras cablear el handler, ref_f08a/ref_f08c son la unica copia que queda de
la logica inline original -- no borrarlo hasta cerrar el paso 2.

NOTA (10/10/2026): se retiro de las tres partes la comparacion del aviso de
camino feliz (`shortfall`). Su emisor, detect_happy_path_shortfall(), quedo
sin llamadas con G1 y se elimino del modulo -- la composicion del resultado
la expresa ahora la ESTRUCTURA del contrato (principal / alternatives), no
una senal que haya que interpretar. El resto sigue siendo copia literal.

ref_f08a() y ref_f08c() son copias LITERALES de la logica inline de
mcp_conversation_handler.py (mismos nombres de variable, mismas condiciones,
mismo orden de operaciones), adaptadas solo en lo minimo para ser funciones
(entradas como parametros, salidas como dict). mod_pipeline() encadena las
funciones del modulo extraido tal y como las usara el llamador real.

Se comparan TODOS los observables de ambas implementaciones sobre casos
aleatorios con los diccionarios reales del repo.
"""
import ast
import random
import sys

sys.path.insert(0, ".")
from src.recommenders import f08_similarity_resolution as m  # noqa: E402

UP = "src/recommenders/"  # ejecutar desde la raiz del repo


def load_literal(path, name):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(getattr(t, "id", None) == name for t in targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


CK = load_literal(UP + "improved_fallback_exclude_seen.py", "CATEGORY_KEYWORDS")
PT = load_literal(UP + "product_taxonomy.py", "PRODUCT_TAXONOMY")


def real_get_parent_categories():
    # Copia exacta de improved_fallback_exclude_seen.get_parent_categories()
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
# REFERENCIA A -- copia literal del bloque F-08 Fase A (lineas ~2563-2945)
# =============================================================================
def ref_f08a(_f08_ptype, _f08_visual_ids, _f08_pid, id_index,
             get_parent_categories_fn, n_recommendations, fill_len,
             last_visual_score):
    out = {}
    _f08_type_upper = _f08_ptype.upper()
    _f08_expanded_cats = [_f08_type_upper] if _f08_type_upper else []
    if _f08_type_upper:
        try:
            _f08_parent_map = get_parent_categories_fn()
            _f08_siblings = next(
                (
                    subs
                    for subs in _f08_parent_map.values()
                    if _f08_type_upper in [s.upper() for s in subs]
                ),
                None,
            )
            if _f08_siblings:
                _f08_expanded_cats = [s.upper() for s in _f08_siblings]
        except Exception:
            _f08_expanded_cats = [_f08_type_upper] if _f08_type_upper else []
    out["categories"] = list(_f08_expanded_cats)

    _f08_same_cat = [
        pid for pid in _f08_visual_ids
        if str(pid) != _f08_pid
        and (
            not _f08_expanded_cats
            or id_index.get(str(pid), {})
               .get("product_type", "").upper() in _f08_expanded_cats
        )
    ]
    out["filtered"] = list(_f08_same_cat)

    _f08_candidate_breakdown = {}
    for _f08_bd_pid in _f08_same_cat:
        _f08_bd_type = (
            id_index.get(str(_f08_bd_pid), {})
            .get("product_type", "").upper()
        )
        _f08_candidate_breakdown[_f08_bd_type] = (
            _f08_candidate_breakdown.get(_f08_bd_type, 0) + 1
        )
    out["breakdown"] = _f08_candidate_breakdown

    _f08_tfidf = True  # en el original: content_recommender (truthy aqui)
    if _f08_type_upper and _f08_tfidf:
        _f08_own_type_items = [
            pid for pid in _f08_same_cat
            if id_index.get(str(pid), {})
               .get("product_type", "").upper() == _f08_type_upper
        ]
        _f08_sibling_items = [
            pid for pid in _f08_same_cat
            if id_index.get(str(pid), {})
               .get("product_type", "").upper() != _f08_type_upper
        ]

        def _f08_interleave_by_subtype(_f08_flat_pids):
            _f08_by_type = {}
            for _f08_st_pid in _f08_flat_pids:
                _f08_st_type = (
                    id_index.get(str(_f08_st_pid), {})
                    .get("product_type", "UNKNOWN").upper()
                )
                _f08_by_type.setdefault(_f08_st_type, []).append(_f08_st_pid)
            _f08_result = []
            while any(_f08_by_type.values()):
                for _f08_st_key, _f08_st_group in list(_f08_by_type.items()):
                    if _f08_st_group:
                        _f08_result.append(_f08_st_group.pop(0))
                    if not _f08_st_group:
                        del _f08_by_type[_f08_st_key]
            return _f08_result

        _f08_same_cat = (
            _f08_own_type_items
            + _f08_interleave_by_subtype(_f08_sibling_items)
        )
    out["ordered"] = list(_f08_same_cat)

    if len(_f08_same_cat) >= n_recommendations:
        out["path"] = "happy"
        out["final"] = _f08_same_cat[:n_recommendations]
    elif len(_f08_same_cat) > 0:
        out["path"] = "partial"
        _f08_fill_events = []
        for _f08_cat in _f08_expanded_cats:
            _f08_fill_events.append({
                "productId": None,
                "product_info": {"product_type": _f08_cat, "source": "f08a_partial_fill"},
                "eventType": "view",
                "source": "f08a_partial_fill",
            })
            if _f08_cat.upper() == _f08_type_upper:
                _f08_fill_events.append({
                    "productId": None,
                    "product_info": {"product_type": _f08_cat,
                                     "source": "f08a_partial_fill_anchor_boost"},
                    "eventType": "view",
                    "source": "f08a_partial_fill",
                })
        out["fill_events"] = _f08_fill_events
        _f08_needed = n_recommendations - len(_f08_same_cat)
        shown_products = set()  # Turn 1: siempre vacio
        out["fill_exclude"] = (
            set(shown_products) | {str(pid) for pid in _f08_same_cat} | {_f08_pid}
        )
        _fill_got = min(fill_len, _f08_needed)
        if _fill_got < _f08_needed:
            _f08_exhausted_cat = (
                _f08_expanded_cats[0] if _f08_expanded_cats else "esta categoria"
            )
            _f08_shown_count = len(_f08_same_cat) + _fill_got
            out["exhaustion"] = {"category": _f08_exhausted_cat,
                                 "shown_count": _f08_shown_count,
                                 "total_count": _f08_shown_count,
                                 # PASO 2 (04/10/2026): campo anadido
                                 # DELIBERADAMENTE al bloque original tambien,
                                 # para que el arnes siga comparando el resto de
                                 # la logica. Es el unico punto en que estas
                                 # referencias dejan de ser copia literal del
                                 # handler previo al paso 2.
                                 "kind": "catalog_exhausted"}
        else:
            out["exhaustion"] = None
        out["fill_score_start"] = (
            round(last_visual_score - 0.05, 4) if last_visual_score is not None else 0.90
        )
    else:
        out["path"] = "empty"
    return out


# =============================================================================
# REFERENCIA C -- copia literal del bloque F-08C (lineas ~1770-2245)
# =============================================================================
def ref_f08c(_c08_ctx_type, query_cats_in, _c08_visual_ids, _c08_pid, id_index,
             get_parent_categories_fn, n_recommendations, shown_products,
             fill_len, last_visual_score):
    out = {}
    _c08_query_cats = list(query_cats_in or [])
    _c08_anchor_type_for_ranking = None
    if not _c08_query_cats:
        if _c08_ctx_type:
            _c08_anchor_type_for_ranking = _c08_ctx_type.upper()
            try:
                _c08_parent_map = get_parent_categories_fn()
                _c08_siblings = next(
                    (
                        subs
                        for subs in _c08_parent_map.values()
                        if _c08_ctx_type.upper()
                        in [s.upper() for s in subs]
                    ),
                    None,
                )
                _c08_query_cats = (
                    _c08_siblings
                    if _c08_siblings
                    else [_c08_ctx_type]
                )
            except Exception:
                _c08_query_cats = [_c08_ctx_type]
    elif _c08_ctx_type and _c08_ctx_type.upper() in [
        c.upper() for c in _c08_query_cats
    ]:
        _c08_anchor_type_for_ranking = _c08_ctx_type.upper()
    out["categories"] = list(_c08_query_cats)
    out["ranking"] = _c08_anchor_type_for_ranking

    _c08_candidates = [
        pid for pid in _c08_visual_ids
        if pid not in shown_products
        and pid != _c08_pid
        and (
            not _c08_query_cats
            or id_index.get(str(pid), {})
               .get("product_type", "").upper()
               in [c.upper() for c in _c08_query_cats]
        )
    ]
    out["filtered"] = list(_c08_candidates)

    _c08_candidate_breakdown = {}
    for _c08_bd_pid in _c08_candidates:
        _c08_bd_type = (
            id_index.get(str(_c08_bd_pid), {})
            .get("product_type", "").upper()
        )
        _c08_candidate_breakdown[_c08_bd_type] = (
            _c08_candidate_breakdown.get(_c08_bd_type, 0) + 1
        )
    out["breakdown"] = _c08_candidate_breakdown

    if _c08_anchor_type_for_ranking:
        _c08_candidates = sorted(
            _c08_candidates,
            key=lambda pid: 0 if (
                id_index.get(str(pid), {})
                .get("product_type", "").upper()
                == _c08_anchor_type_for_ranking
            ) else 1,
        )
    out["ordered"] = list(_c08_candidates)

    if len(_c08_candidates) >= n_recommendations:
        out["path"] = "happy"
        out["final"] = _c08_candidates[:n_recommendations]
    elif len(_c08_candidates) > 0:
        out["path"] = "partial"
        # NOTA: el original usa mcp_context.current_product_context["product_type"],
        # que es la misma fuente que _c08_ctx_type.
        _c08_current_type = str(_c08_ctx_type).upper()
        _c08_fill_events = []
        for _c08_cat in _c08_query_cats:
            _c08_fill_events.append({
                "productId": None,
                "product_info": {"product_type": _c08_cat, "source": "f08c_partial_fill"},
                "eventType": "view",
                "source": "f08c_partial_fill",
            })
            if _c08_cat.upper() == _c08_current_type:
                _c08_fill_events.append({
                    "productId": None,
                    "product_info": {"product_type": _c08_cat,
                                     "source": "f08c_partial_fill_anchor_boost"},
                    "eventType": "view",
                    "source": "f08c_partial_fill",
                })
        out["fill_events"] = _c08_fill_events
        _c08_needed = n_recommendations - len(_c08_candidates)
        out["fill_exclude"] = (
            set(shown_products) | {str(pid) for pid in _c08_candidates} | {_c08_pid}
        )
        _fill_got = min(fill_len, _c08_needed)
        if _fill_got < _c08_needed:
            _c08_exhausted_cat = (
                _c08_query_cats[0] if _c08_query_cats else "esta categoria"
            )
            _c08_shown_count = len(_c08_candidates) + _fill_got
            out["exhaustion"] = {"category": _c08_exhausted_cat,
                                 "shown_count": _c08_shown_count,
                                 "total_count": _c08_shown_count,
                                 # PASO 2 (04/10/2026): ver nota en ref_f08a.
                                 "kind": "catalog_exhausted"}
        else:
            out["exhaustion"] = None
        out["fill_score_start"] = (
            round(last_visual_score - 0.05, 4) if last_visual_score is not None else 0.90
        )
    else:
        out["path"] = "empty"
    return out


# =============================================================================
# Pipeline con el modulo extraido (como lo cableara el llamador)
# =============================================================================
def mod_pipeline(route, anchor_type, query_cats, visual_ids, anchor_pid, id_index,
                 parent_fn, n, shown, fill_len, last_visual_score):
    type_of = lambda pid: id_index.get(str(pid), {}).get("product_type", "")  # noqa: E731
    out = {}
    res = m.resolve_similarity_categories(route, anchor_type, query_cats, parent_fn)
    out["categories"] = list(res.categories)
    if route is m.F08C_ROUTE:
        out["ranking"] = res.anchor_type_for_ranking
    exclude = shown if route is m.F08C_ROUTE else set()
    filtered = m.filter_visual_candidates(visual_ids, anchor_pid, res.categories, type_of, exclude)
    out["filtered"] = list(filtered)
    out["breakdown"] = m.candidate_breakdown(filtered, type_of)
    ordered = m.order_candidates(route, filtered, res.anchor_type_for_ranking, type_of)
    out["ordered"] = list(ordered)
    path = m.classify_pool(len(ordered), n)
    out["path"] = path
    if path == m.POOL_HAPPY:
        out["final"] = ordered[:n]
    elif path == m.POOL_PARTIAL:
        out["fill_events"] = m.build_partial_fill_events(
            route, res.categories, str(anchor_type).upper())
        needed = n - len(ordered)
        out["fill_exclude"] = m.build_fill_exclusion(exclude, ordered, anchor_pid)
        out["exhaustion"] = m.build_partial_exhaustion_info(
            res.categories, len(ordered), min(fill_len, needed), needed)
        out["fill_score_start"] = m.fill_score_start(last_visual_score)
    return out


def main(n_cases=20000, seed=20261002):
    rng = random.Random(seed)
    real_types = list(PT.keys())
    weird_types = ["AROMAS", "PACK", "Aros", "collares", ""]  # stress: minusculas, sin tipo
    id_index = {}
    for i in range(400):
        t = rng.choice(real_types * 6 + weird_types)
        prod = {"id": str(i)}
        if not (t == "" and rng.random() < 0.5):  # a veces sin clave product_type
            prod["product_type"] = t
        id_index[str(i)] = prod
    missing_ids = [f"m{i}" for i in range(20)]  # IDs fuera del indice TF-IDF
    all_ids = list(id_index.keys()) + missing_ids
    anchors = real_types + ["", "Aros", "capas gasa", "TURBANTES", "AROMAS"]
    all_cat_names = real_types + ["aros", "Collares", "NOVIAS CONJUNTOS FALDAS"]

    counts = {"A": 0, "C": 0}
    paths = {}
    for case in range(n_cases):
        anchor_type = rng.choice(anchors)
        anchor_pid = rng.choice(all_ids)
        k = rng.randint(0, 50)
        visual_ids = rng.sample(all_ids, k)
        if rng.random() < 0.3:  # el propio ancla dentro de su pool (caso real)
            visual_ids.insert(rng.randint(0, len(visual_ids)), anchor_pid)
        n = rng.randint(1, 10)
        r = rng.random()
        parent_fn = (failing_parent_fn if r < 0.1
                     else make_shuffled_parent_fn(rng) if r < 0.3
                     else real_get_parent_categories)
        fill_len = rng.randint(0, 10)
        last_score = rng.choice([None, 1.0, 0.94, 0.85, 0.7666])

        # --- Ruta A ---
        ref = ref_f08a(anchor_type, visual_ids, str(anchor_pid), id_index,
                       parent_fn, n, fill_len, last_score)
        got = mod_pipeline(m.F08A_ROUTE, anchor_type, None, visual_ids, str(anchor_pid),
                           id_index, parent_fn, n, set(), fill_len, last_score)
        assert ref == got, f"A diverge en caso {case}: anchor={anchor_type!r}\nref={ref}\ngot={got}"
        counts["A"] += 1
        paths["A:" + ref["path"]] = paths.get("A:" + ref["path"], 0) + 1

        # --- Ruta C ---
        qmode = rng.random()
        if qmode < 0.5:
            query_cats = []
        else:
            query_cats = rng.sample(all_cat_names, rng.randint(1, 5))
            if anchor_type and rng.random() < 0.4:
                query_cats.append(anchor_type)  # caso FIX 18/07 (ancla incluida)
        shown = set(rng.sample(all_ids, rng.randint(0, 40)))
        ref = ref_f08c(anchor_type, query_cats, visual_ids, str(anchor_pid), id_index,
                       parent_fn, n, shown, fill_len, last_score)
        got = mod_pipeline(m.F08C_ROUTE, anchor_type, query_cats, visual_ids, str(anchor_pid),
                           id_index, parent_fn, n, shown, fill_len, last_score)
        assert ref == got, f"C diverge en caso {case}: anchor={anchor_type!r} q={query_cats}\nref={ref}\ngot={got}"
        counts["C"] += 1
        paths["C:" + ref["path"]] = paths.get("C:" + ref["path"], 0) + 1

    print(f"OK -- {counts['A']} casos A + {counts['C']} casos C, 0 divergencias")
    print("cobertura de caminos:", dict(sorted(paths.items())))


if __name__ == "__main__":
    main()
