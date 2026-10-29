"""
Oraculo de equivalencia del filtro DENTRO de la busqueda -- E5 nivel 2, paso 3
(26/10/2026). Spec: SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md, secciones 3 y 8.2.

Uso (desde la raiz del repo):  python tests/characterization/equiv_harness_e5.py
No es un test de pytest (nombre sin prefijo test_): es un ORACULO, igual que
equiv_harness_f08.py y equiv_harness_pool_request.py.

QUE DEMUESTRA
-------------
Que build_visual_filter() (aplicado ANTES de buscar) decide exactamente lo
mismo que filter_visual_candidates() (aplicado DESPUES), usando la funcion
REAL del modulo:

  P1 (por elemento): para el ranking COMPLETO L del indice,
        filter_visual_candidates(L, ancla, cats, type_of, vistos)
        == [p for p in L if F.admits(p)]
     Si se cumple para todo p, el filtro se puede adelantar.
  P2 (pool infinito): la busqueda filtrada con k resultados
        == filter_visual_candidates(L, ...)[:k]
  P3 (prefijo): lo que hoy se obtiene con un pool finito (top_k, filtrado
     despues) es PREFIJO de lo que da el filtro dentro de la busqueda: el
     nivel 2 nunca quita nada de lo que hoy se muestra; solo anade.

Casos generados: tipos en minusculas y vacios, productos SIN product_type,
ids del indice que el catalogo no conoce, el ancla dentro del pool,
categorias vacias (sin restriccion) y vistos de 0 a 60.

Fuera de P1 por diseno (documentado en build_visual_filter): un product_type
None. filter_visual_candidates() fallaria solo si ese producto entra en el
pool; build_visual_filter() lo trata como "sin tipo". Cubierto por un test
unitario, no por este oraculo.

AUTO-VERIFICACION: tras la comparacion principal se ejecutan MUTANTES de
build_visual_filter (defectos plausibles) y se exige que cada uno sea
detectado. Si alguno sobrevive, el oraculo no es fiable y el script falla.
"""
import random
import sys

sys.path.insert(0, ".")
from src.recommenders import f08_similarity_resolution as m  # noqa: E402

TYPES = ["AROS", "COLLARES", "CARTERAS", "CLUTCH", "VESTIDOS CORTOS",
         "Aros", "collares", "", "PACK"]   # minusculas y vacio a proposito
CAT_POOL = ["AROS", "COLLARES", "CARTERAS", "CLUTCH", "VESTIDOS CORTOS", "aros"]


def make_case(rng):
    """Catalogo (id_index), ranking completo del indice, ancla, cats, vistos."""
    id_index = {}
    for i in range(120):
        t = rng.choice(TYPES)
        prod = {"id": str(i)}
        if not (t == "" and rng.random() < 0.5):   # a veces sin la clave
            prod["product_type"] = t
        id_index[str(i)] = prod
    # indice: casi todo el catalogo + 8 ids que el catalogo no conoce
    ranking = [str(i) for i in range(120) if rng.random() < 0.95] + [f"m{i}" for i in range(8)]
    rng.shuffle(ranking)                            # = orden de similitud con el ancla
    anchor = rng.choice(ranking)
    cats = rng.sample(CAT_POOL, rng.choice([0, 1, 2, 3]))
    shown = set(rng.sample(ranking, rng.randint(0, 60)))
    return id_index, ranking, anchor, cats, shown


def check(build_fn, n_cases, seed, stop_at_first=False):
    """Devuelve (fallos_por_propiedad, n_casos)."""
    rng = random.Random(seed)
    fails = {"P1": 0, "P2": 0, "P3": 0}
    for _ in range(n_cases):
        id_index, ranking, anchor, cats, shown = make_case(rng)

        def type_of(pid, _ix=id_index):   # misma forma que el handler
            return _ix.get(str(pid), {}).get("product_type", "")

        f = build_fn(id_index.keys(), cats, anchor, type_of, shown)
        ref = m.filter_visual_candidates(ranking, anchor, cats, type_of, shown)
        got = [p for p in ranking if f.admits(p)]
        if ref != got:
            fails["P1"] += 1
        else:
            k = rng.randint(1, 140)
            filtered_search = got[:k]                       # lo que hace FAISS con el selector
            if filtered_search != ref[:k]:
                fails["P2"] += 1
            top_k = rng.randint(1, 140)
            today = m.filter_visual_candidates(ranking[:top_k], anchor, cats, type_of, shown)
            if filtered_search[:len(today)] != today[:len(filtered_search)]:
                fails["P3"] += 1
        if stop_at_first and sum(fails.values()):
            break
    return fails


# ── Mutantes: defectos plausibles que el oraculo DEBE detectar ──────────────
def _mut(transform):
    def build(*a):
        return transform(m.build_visual_filter(*a), *a)
    return build


MUTANTS = {
    # Categorias vacias tratadas como "todo el catalogo" (excluiria los ids
    # del indice que el catalogo no conoce).
    "cats vacias = todo el catalogo": lambda ids, cats, anchor, type_of, shown: (
        m.VisualFilter(include=frozenset(str(i) for i in ids),
                       exclude=frozenset(map(str, shown)) | {str(anchor)})
        if not cats else m.build_visual_filter(ids, cats, anchor, type_of, shown)),
    # Comparacion de tipo sin mayusculas.
    "tipo sin mayusculas": lambda ids, cats, anchor, type_of, shown: (
        m.VisualFilter(include=frozenset(str(i) for i in ids if type_of(i) in set(cats)) if cats else None,
                       exclude=frozenset(map(str, shown)) | {str(anchor)})),
    # Olvidar excluir el ancla.
    "ancla no excluida": _mut(lambda f, ids, cats, anchor, type_of, shown:
                              m.VisualFilter(include=f.include, exclude=f.exclude - {str(anchor)})),
    # Olvidar excluir los vistos.
    "vistos no excluidos": _mut(lambda f, ids, cats, anchor, type_of, shown:
                                m.VisualFilter(include=f.include, exclude=frozenset({str(anchor)}))),
    # Ignorar las categorias.
    "categorias ignoradas": _mut(lambda f, ids, cats, anchor, type_of, shown:
                                 m.VisualFilter(include=None, exclude=f.exclude)),
}


def self_check_mutants(n_cases=3000, seed=26102026):
    survivors = []
    for name, mutant in MUTANTS.items():
        fails = check(mutant, n_cases, seed, stop_at_first=True)
        detected = sum(fails.values()) > 0
        print(f"  mutante {name!r}: {'detectado' if detected else 'SOBREVIVE'}")
        if not detected:
            survivors.append(name)
    return survivors


def main(n_cases=20000, seed=20261026):
    fails = check(m.build_visual_filter, n_cases, seed)
    print(f"{n_cases} casos -> fallos: {fails}")
    if sum(fails.values()):
        sys.exit(1)
    print("OK -- P1, P2 y P3 se cumplen en todos los casos")
    print("auto-verificacion por mutantes:")
    survivors = self_check_mutants()
    if survivors:
        print(f"ORACULO NO FIABLE -- mutantes supervivientes: {survivors}")
        sys.exit(2)
    print(f"OK -- {len(MUTANTS)}/{len(MUTANTS)} mutantes detectados")


if __name__ == "__main__":
    main()
