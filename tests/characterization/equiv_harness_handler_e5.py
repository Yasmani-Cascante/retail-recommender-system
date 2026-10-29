"""
Prueba DIFERENCIAL del handler -- E5 nivel 2, paso 3 (26/10/2026).
Spec: SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md, seccion 6.3.

Uso (desde la raiz del repo):
    python tests/characterization/equiv_harness_handler_e5.py <handler_base.py>
<handler_base.py> es una copia del handler ANTES del paso 3. En Windows,
generala SIN pasar por PowerShell: su `>` la guarda en UTF-16 y CORROMPE las
tildes y los simbolos, y los bloques no se encontrarian (ver read_source en
equiv_harness_handler_e5_blocks.py):
    cmd /c "git show <commit_anterior>:src/api/core/mcp_conversation_handler.py > base.py"
No es un test de pytest: es un ORACULO, como equiv_harness_f08.py.

QUE HACE
--------
Extrae del codigo REAL los dos bloques que cambia el paso 3 -- F-08C (turno 2+)
y F-08 Fase A (turno 1) -- en su version BASE y en la ACTUAL, los convierte en
funciones y los ejecuta con las MISMAS entradas. Todo lo que decide el
resultado es real: los bloques, f08_similarity_resolution, product_taxonomy,
recommendation_set, extract_categories_from_query, get_parent_categories y
normalize_recommendation_dict. Solo se simula lo externo:
  - el embedding-service: un indice DETERMINISTA cuyo search_filtered aplica de
    verdad include/exclude/top_k (la semantica ya validada del servicio);
  - el relleno de catalogo (smart_fallback): DETERMINISTA, mismos argumentos;
  - el contexto de la conversacion.

PROPIEDADES
-----------
  D1 Flag DESACTIVADO: base == actual en el valor devuelto, en las llamadas al
     servicio visual y al relleno, y en los logs (mismo texto, mismo orden).
  D2 Flag ACTIVADO, con top_k que alcanza a todos los elegibles: actual ==
     base con pool INFINITO (P2 al nivel del handler). Se compara el valor
     devuelto sin el campo visual_rank, que cambia de significado a proposito
     (posicion entre elegibles) y que ningun consumidor lee (verificado).
  D3 Flag ACTIVADO, nada elegible (rama vacia, F7): mismo resultado que la base
     y, en Fase A, SIN fallback por imagen.
  En D2 y D3 se exige ademas que NO aparezca el aviso "E5 divergencia": el
  filtro posterior se conserva como defensa y oculta en el resultado un filtro
  mal construido; el aviso es la unica senal (ver diverged()).
  D4 Flag ACTIVADO, el servicio falla (None): mismo resultado que la base.
Auto-verificacion: mutantes del bloque ACTUAL (defectos plausibles) que deben
ser detectados.
"""
import asyncio
import copy
import hashlib
import logging
import os
import random
import sys
import types

sys.path.insert(0, ".")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import src.recommenders.improved_fallback_exclude_seen as ifs  # noqa: E402
from equiv_harness_handler_e5_blocks import as_function, extract  # noqa: E402

CURRENT = "src/api/core/mcp_conversation_handler.py"
TYPES = ["AROS", "COLLARES", "BRAZALETES", "CARTERAS", "CLUTCH", "CINTURONES",
         "PANTALONES", "FALDAS", "LEGGINGS", "VESTIDOS CORTOS", "VESTIDOS LARGOS",
         "NOVIAS CORTOS", "CHAQUETAS", "TOPS"]
FALLTHROUGH = object()


# ── Entorno simulado ────────────────────────────────────────────────────────
def make_catalog(rng, n=240):
    prods = []
    for i in range(n):
        t = rng.choice(TYPES)
        prods.append({"id": f"{9000000 + i}", "title": f"Prod {i}", "product_type": t,
                      "body_html": "", "price": "10.0", "images": [], "variants": [],
                      # image_url: sin ella el fallback por imagen de Fase A nunca se
                      # ejercia (hueco detectado por un mutante superviviente).
                      "image_url": f"https://cdn.example/{9000000 + i}.jpg"})
    return prods


class FakeTfidf:
    def __init__(self, products):
        self.product_data = products
        self.id_index = {p["id"]: p for p in products}


class FakeColbert:
    """Indice determinista: el ranking de cada ancla es un orden pseudoaleatorio
    fijo de todos los ids del indice (incluidos ids que el catalogo no conoce).
    `infinite` ignora top_k (pool infinito para D2)."""
    def __init__(self, index_ids, fail=False, infinite=False):
        self.index_ids, self.fail, self.infinite, self.calls = list(index_ids), fail, infinite, []

    def _ranking(self, anchor, boost=""):
        key = lambda i: hashlib.md5(f"{anchor}|{boost}|{i}".encode()).hexdigest()
        ids = sorted((i for i in self.index_ids if i != anchor), key=key)
        return [(pid, round(0.99 - 0.001 * r, 6)) for r, pid in enumerate(ids)]

    async def search_by_product_id(self, pid, top_k=8, with_scores=False):
        self.calls.append(("by_id", pid, top_k))
        if self.fail: return None
        if pid not in self.index_ids: return []
        r = self._ranking(pid)
        return r if self.infinite else r[:top_k]

    async def search_by_product_id_with_text_boost(self, pid, boost_text, alpha=0.5, top_k=8, with_scores=False):
        self.calls.append(("text_boost", pid, boost_text, alpha, top_k))
        if self.fail: return None
        if pid not in self.index_ids: return []
        r = self._ranking(pid, boost_text)
        return r if self.infinite else r[:top_k]

    async def search_by_image(self, image_bytes, top_k=8, with_scores=False):
        self.calls.append(("by_image", top_k))
        return [] if self.fail else self._ranking("IMG")[:top_k]

    async def search_filtered(self, pid, include_ids=None, exclude_ids=None, top_k=100, boost_text=None, alpha=0.5):
        from src.api.services.colbert_client import FilteredVisualResult
        self.calls.append(("filtered", pid, None if include_ids is None else tuple(sorted(include_ids)),
                           tuple(sorted(exclude_ids or [])), top_k, boost_text, alpha))
        if self.fail: return None
        if pid not in self.index_ids:
            return FilteredVisualResult([], False, 0, 0)
        inc = None if include_ids is None else set(include_ids)
        exc = set(exclude_ids or []) | {pid}
        adm = [(p, s) for p, s in self._ranking(pid, boost_text or "")
               if p not in exc and (inc is None or p in inc)]
        known = set(self.index_ids)
        unknown = 0 if inc is None else sum(1 for i in inc if i not in known)
        return FilteredVisualResult(adm[:top_k], True, len(adm), unknown)


def make_fallback(catalog_types):
    calls = []

    class FakeFallback:
        @staticmethod
        async def smart_fallback(user_id, products, user_events=None, n=5, exclude_products=None,
                                 user_query=None, strict_category=False):
            wanted = {str((e.get("product_info") or {}).get("product_type", "")).upper() for e in (user_events or [])}
            excl = set(map(str, exclude_products or []))
            calls.append(("smart_fallback", tuple(sorted(wanted)), n, tuple(sorted(excl)), strict_category))
            out = [p for p in sorted(products, key=lambda p: p["id"])
                   if p.get("product_type", "").upper() in wanted and p["id"] not in excl]
            return [copy.deepcopy(p) for p in out[:n]]
    return FakeFallback, calls


class FakeHttpClient:
    """Sustituye a httpx.AsyncClient en la descarga de la imagen del fallback
    de Fase A (sin red en las pruebas)."""
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    async def get(self, url):
        return types.SimpleNamespace(raise_for_status=lambda: None, content=b"IMG")


class ListHandler(logging.Handler):
    def __init__(self): super().__init__(); self.msgs = []
    def emit(self, record): self.msgs.append((record.levelname, record.getMessage()))


def install_router_stub(client):
    for name in ("src.api.routers",):
        sys.modules.setdefault(name, types.ModuleType(name))
    mod = types.ModuleType("src.api.routers.visual_search_router")
    mod._get_colbert_client = lambda: client
    sys.modules["src.api.routers.visual_search_router"] = mod


async def run_block(fn_src, scen, client):
    """Ejecuta un bloque extraido con el escenario dado. Devuelve (resultado, logs)."""
    install_router_stub(client)
    tfidf = FakeTfidf(scen["catalog"])
    fb_cls, fb_calls = make_fallback(TYPES)
    lg = logging.getLogger(f"harness.{id(fn_src)}.{random.random()}")
    lg.propagate = False; h = ListHandler(); lg.addHandler(h); lg.setLevel(logging.DEBUG)
    ifs_logger = logging.getLogger(ifs.__name__); ifs_logger.addHandler(h); ifs_logger.setLevel(logging.DEBUG)
    ctx = types.SimpleNamespace(current_product_context={"id": scen["anchor"], "product_type": scen["anchor_type"]})
    g = {
        "os": os, "asyncio": asyncio, "logger": lg,
        "mcp_context": ctx, "conversation_query": scen["query"],
        "shown_products": set(scen["shown"]), "use_diversification": scen["route"] == "C",
        "_is_visual_similarity_query": lambda q: True,
        "main_unified_redis": types.SimpleNamespace(hybrid_recommender=types.SimpleNamespace(content_recommender=tfidf)),
        "all_products": tfidf.product_data,
        "extract_categories_from_query": ifs.extract_categories_from_query,
        "get_parent_categories": ifs.get_parent_categories,
        "normalize_recommendation_dict": ifs.normalize_recommendation_dict,
        "ImprovedFallbackStrategies": fb_cls,
        "n_recommendations": scen["n"], "validated_user_id": "u1",
        "__FALLTHROUGH__": FALLTHROUGH,
    }
    exec(compile(fn_src, f"<bloque {scen['route']}>", "exec"), g)
    # Fase A importa la clase REAL ImprovedFallbackStrategies dentro del bloque
    # (no usa el nombre externo), y su smart_fallback real usa random.sample:
    # sin sustituirlo EN LA CLASE, la misma version ejecutada dos veces devuelve
    # productos distintos (comprobado). Se sustituye el metodo en la clase real
    # durante la ejecucion y se restaura despues.
    real_sf = ifs.ImprovedFallbackStrategies.__dict__["smart_fallback"]
    ifs.ImprovedFallbackStrategies.smart_fallback = staticmethod(fb_cls.smart_fallback)
    import httpx
    real_ac, httpx.AsyncClient = httpx.AsyncClient, FakeHttpClient
    try:
        res = await g["__block"]()
    finally:
        ifs.ImprovedFallbackStrategies.smart_fallback = real_sf
        httpx.AsyncClient = real_ac
        ifs_logger.removeHandler(h)
    return res, h.msgs, fb_calls


def diverged(logs):
    """Invariante: con el filtro DENTRO de la busqueda bien construido, el
    filtro posterior (que se conserva como defensa) no quita nada y el aviso
    "E5 divergencia" no aparece nunca. Si aparece, el filtro admitio algo que
    no debia -- aunque la defensa lo retire y el resultado final no cambie."""
    return any("E5 divergencia" in m for _, m in logs)


def strip_rank(res):
    if res is FALLTHROUGH or not isinstance(res, list): return res
    return [{k: v for k, v in r.items() if k != "visual_rank"} if isinstance(r, dict) else r for r in res]


def scenario(rng, route):
    catalog = make_catalog(rng)
    ids = [p["id"] for p in catalog]
    index_ids = [i for i in ids if rng.random() < 0.95] + [f"UNK{i}" for i in range(5)]
    anchor = rng.choice(ids)
    anchor_type = next(p["product_type"] for p in catalog if p["id"] == anchor)
    q = rng.choice(["muéstrame productos similares", "algo parecido a esto",
                    "muéstrame aros similares", "quiero faldas parecidas"]) if route == "C" else "muéstrame productos similares"
    shown = rng.sample(ids, rng.choice([0, 0, 5, 30, 80])) if route == "C" else []
    return {"route": route, "catalog": catalog, "index_ids": index_ids, "anchor": anchor,
            "anchor_type": anchor_type, "query": q, "shown": shown, "n": 8}


def set_env(filter_on, base=None, cap=None):
    os.environ["VISUAL_SEARCH_ENABLED"] = "true"
    os.environ["RECS_VISUAL_FILTER_IN_SEARCH"] = "1" if filter_on else "0"
    for k, v in (("RECS_VISUAL_POOL_BASE", base), ("RECS_VISUAL_POOL_CAP", cap)):
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = str(v)


async def compare(base_src, cur_src, n_cases, seed, verbose=True):
    rng = random.Random(seed)
    fails = {"D1": 0, "D2": 0, "D3": 0, "D4": 0}
    paths = {}
    first = {}
    for case in range(n_cases):
        route = "C" if case % 2 == 0 else "A"
        sc = scenario(rng, route)
        bsrc, csrc = base_src[route], cur_src[route]

        # D1 -- flag desactivado: todo identico
        set_env(False)
        cb, cc = FakeColbert(sc["index_ids"]), FakeColbert(sc["index_ids"])
        rb, lb, fb = await run_block(bsrc, sc, cb)
        rc, lc, fc = await run_block(csrc, sc, cc)
        if (rb, cb.calls, fb, lb) != (rc, cc.calls, fc, lc):
            fails["D1"] += 1; first.setdefault("D1", (case, route))
        key = f"{route}:{'contrato' if rb is not FALLTHROUGH else 'fallthrough'}"
        paths[key] = paths.get(key, 0) + 1
        if any(c[0] == "by_image" for c in cb.calls):   # cobertura del fallback por imagen
            paths["A:fallback_por_imagen"] = paths.get("A:fallback_por_imagen", 0) + 1

        # D2 -- flag activado, top_k que alcanza a todos los elegibles == base con pool infinito
        set_env(False, base=5000, cap=5000)
        rb, _, fb = await run_block(bsrc, sc, FakeColbert(sc["index_ids"], infinite=True))
        set_env(True, base=5000, cap=5000)
        cc = FakeColbert(sc["index_ids"])
        rc, lc, fc = await run_block(csrc, sc, cc)
        if (strip_rank(rb) != strip_rank(rc) or fb != fc or not any(c[0] == "filtered" for c in cc.calls)
                or diverged(lc)):
            fails["D2"] += 1; first.setdefault("D2", (case, route))

        # D3 -- rama vacia: todo lo admisible ya visto
        sc3 = dict(sc, shown=[i for i in sc["index_ids"] if i != sc["anchor"]])
        set_env(False, base=5000, cap=5000)
        rb, _, fb = await run_block(bsrc, sc3, FakeColbert(sc["index_ids"], infinite=True))
        set_env(True)
        cc = FakeColbert(sc["index_ids"])
        rc, lc, fc = await run_block(csrc, sc3, cc)
        anchor_indexed = sc["anchor"] in sc["index_ids"]
        image_calls = [c for c in cc.calls if c[0] == "by_image"]
        if strip_rank(rb) != strip_rank(rc) or fb != fc or (anchor_indexed and image_calls) or diverged(lc):
            fails["D3"] += 1; first.setdefault("D3", (case, route))

        # D4 -- el servicio falla
        set_env(False)
        rb, _, fb = await run_block(bsrc, sc, FakeColbert(sc["index_ids"], fail=True))
        set_env(True)
        rc, _, fc = await run_block(csrc, sc, FakeColbert(sc["index_ids"], fail=True))
        if rb != rc or fb != fc:
            fails["D4"] += 1; first.setdefault("D4", (case, route))
    set_env(False)
    if verbose:
        print(f"{n_cases} escenarios -> fallos: {fails}" + (f" | primer fallo: {first}" if first else ""))
        print("caminos cubiertos (flag desactivado):", dict(sorted(paths.items())))
    return fails


MUTANTS = {
    # Entrar al bloque solo con resultados (olvidar anchor_found): rompe D3.
    "C: entrada sin anchor_found": ("C", "if (_c08_visual_ids or _c08_anchor_found) and _c08_tfidf", "if (_c08_visual_ids) and _c08_tfidf"),
    # Fallback por imagen aunque el ancla este indexada: rompe D3 en Fase A.
    "A: fallback por imagen sin anchor_found": ("A", "if not _f08_visual_raw and not _f08_anchor_found:", "if not _f08_visual_raw:"),
    # Filtrar con las categorias de la resolucion en vez de pool_cats: rompe D2.
    "C: criterio del filtro sin pool_cats": ("C", "_c08_prepared[2].pool_cats or _c08_prepared[1].categories", "_c08_prepared[1].categories"),
    # Preparar SIEMPRE antes de buscar (con el flag desactivado tambien): rompe D1 (orden de logs).
    "C: preparar siempre antes de buscar": ("C", "_c08_prepared = _c08_prepare_pool_request() if _c08_filter_on else None", "_c08_prepared = _c08_prepare_pool_request()"),
    # Olvidar excluir los vistos en el filtro: rompe D2.
    "A: filtro sin vistos": ("A", "                    _f08_type_of,\n                    shown_products,\n                )\n                _f08_fres",
                             "                    _f08_type_of,\n                    [],\n                )\n                _f08_fres"),
}


async def main():
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(2)
    base_src = {r: as_function(extract(sys.argv[1], r)[0]) for r in ("C", "A")}
    cur_src = {r: as_function(extract(CURRENT, r)[0]) for r in ("C", "A")}
    fails = await compare(base_src, cur_src, n_cases=400, seed=20261026)
    if sum(fails.values()):
        sys.exit(1)
    print("OK -- D1, D2, D3 y D4 en todos los escenarios")
    print("auto-verificacion por mutantes:")
    survivors = []
    for name, (route, old, new) in MUTANTS.items():
        assert cur_src[route].count(old) == 1, f"patron del mutante no unico: {name}"
        mut = dict(cur_src); mut[route] = cur_src[route].replace(old, new)
        f = await compare(base_src, mut, n_cases=60, seed=7, verbose=False)
        ok = sum(f.values()) > 0
        print(f"  mutante {name!r}: {'detectado' if ok else 'SOBREVIVE'} {f if ok else ''}")
        if not ok: survivors.append(name)
    if survivors:
        print(f"ORACULO NO FIABLE -- supervivientes: {survivors}"); sys.exit(2)
    print(f"OK -- {len(MUTANTS)}/{len(MUTANTS)} mutantes detectados")


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.CRITICAL)
    asyncio.run(main())
