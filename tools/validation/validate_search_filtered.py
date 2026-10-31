"""
validate_search_filtered.py -- validacion EN PRODUCCION del paso 1 de E5 nivel 2
(22/10/2026). Herramienta de diagnostico, versionada en tools/validation/
el 30/10/2026 (ver README.md de esa carpeta).

Dos modos:
  baseline  ANTES de desplegar: guarda lo que devuelve HOY /search-by-id para
            las anclas de referencia (fichero baseline_search_by_id.json).
  c1        Solo la comprobacion C1 (para una revision SIN el endpoint nuevo,
            p. ej. la imagen antigua redesplegada con otra configuracion).
  check     DESPUES de desplegar: comprueba que
              C1. /search-by-id NO ha cambiado respecto al baseline
                  (el endpoint existente no debe verse afectado);
              C2. /search-filtered sin filtro == /search-by-id;
              C3. con include_ids: resultado == ranking completo filtrado
                  despues (propiedad P2 de la spec), eligible y unknown;
              C4. solo exclusiones: los excluidos desaparecen y el resto
                  conserva su orden;
              C5. ancla desconocida -> anchor_found=false, sin error;
              C6. nada elegible -> anchor_found=true, lista vacia;
              C7. ids desconocidos en include se cuentan en unknown_ids.

EMPATES: dos productos con vectores identicos (p. ej. la misma foto) tienen la
misma puntuacion y FAISS puede ordenarlos distinto en dos busquedas sin que sea
un error. same_ranking() solo acepta un orden distinto cuando las puntuaciones
son iguales, y lo informa.

USO (desde la raiz del repo; el Python de venv_fase0 ya tiene httpx):
  .\\src\\api\\services\\embedding-service\\venv_fase0\\Scripts\\python.exe tools\\validation\\validate_search_filtered.py baseline
  .\\src\\api\\services\\embedding-service\\venv_fase0\\Scripts\\python.exe tools\\validation\\validate_search_filtered.py check
Autenticacion: token de identidad de gcloud (el servicio es --no-allow-unauthenticated).
"""
import json
import subprocess
import sys
from pathlib import Path

import httpx

BASE_URL = "https://retail-embedding-service-178362262166.us-central1.run.app"
# Anclas de referencia: las del guion de validacion del paso 2 (consta en los
# logs que estan en el indice). Ids de Shopify consultados el 22/10/2026.
ANCHORS = {
    "CARTERAS (Bolso Indio Riva Rombos Dorado)": "9978484031797",
    "PANTALONES (Palazzo Silvia Negro)": "9978565329205",
    "AROS (Aros Alana Multicolor Rosado)": "9978475839797",
}
K = 200  # tamano del ranking de referencia
BASELINE = Path(__file__).with_name("baseline_search_by_id.json")
TIMEOUT_S = 300  # min-instances 0: la primera llamada puede esperar un arranque en frio
SCORE_TOL = 1e-5


def make_client() -> httpx.Client:
    # shell=True: en Windows "gcloud" es gcloud.cmd y lo resuelve cmd.exe
    token = subprocess.run("gcloud auth print-identity-token", shell=True,
                           capture_output=True, text=True, check=True).stdout.strip()
    return httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"},
                        timeout=TIMEOUT_S)


def by_id(client, pid, k=K):
    r = client.get("/v1/embed/search-by-id", params={"product_id": pid, "top_k": k})
    r.raise_for_status()
    body = r.json()
    return body["product_ids"], body["scores"]


def filtered(client, pid, **payload):
    r = client.post("/v1/embed/search-filtered", json={"product_id": pid, **payload})
    r.raise_for_status()
    return r.json()


def same_ranking(ids_a, sc_a, ids_b, sc_b):
    """(iguales, empates_reordenados). Iguales si las puntuaciones coinciden
    posicion a posicion y, donde los ids difieren, el bloque de puntuacion
    empatada contiene los mismos ids."""
    if len(ids_a) != len(ids_b):
        return False, 0
    if any(abs(x - y) > SCORE_TOL for x, y in zip(sc_a, sc_b)):
        return False, 0
    ties, i = 0, 0
    while i < len(ids_a):
        j = i
        while j + 1 < len(ids_a) and abs(sc_a[j + 1] - sc_a[i]) <= SCORE_TOL:
            j += 1
        if ids_a[i:j + 1] != ids_b[i:j + 1]:
            if set(ids_a[i:j + 1]) != set(ids_b[i:j + 1]):
                return False, 0
            ties += 1
        i = j + 1
    return True, ties


def baseline(client):
    data = {}
    for name, pid in ANCHORS.items():
        ids, sc = by_id(client, pid)
        if not ids:
            sys.exit(f"ABORTADO: {name} ({pid}) devuelve 0 resultados: no esta en el indice")
        data[pid] = {"product_ids": ids, "scores": sc}
        print(f"  {name}: {len(ids)} resultados guardados")
    BASELINE.write_text(json.dumps(data), encoding="utf-8")
    print(f"\nBaseline en {BASELINE}")


def check(client):
    if not BASELINE.exists():
        sys.exit(f"ABORTADO: falta {BASELINE}. Ejecuta antes el modo baseline.")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    results = []

    def report(code, name, ok, detail=""):
        results.append(ok)
        print(f"  [{'OK ' if ok else 'FALLO'}] {code} {name}{(' -- ' + detail) if detail else ''}")

    for name, pid in ANCHORS.items():
        print(f"\n{name} -- {pid}")
        ids, sc = by_id(client, pid)

        ok, ties = same_ranking(base[pid]["product_ids"], base[pid]["scores"], ids, sc)
        report("C1", "/search-by-id igual que antes del despliegue", ok,
               f"{ties} empate(s) reordenado(s)" if ties else "")

        f = filtered(client, pid, top_k=K)
        ok, ties = same_ranking(ids, sc, f["product_ids"], f["scores"])
        report("C2", "/search-filtered sin filtro == /search-by-id",
               ok and f["anchor_found"], f"{ties} empate(s)" if ties else "")

        include = ids[10::3]
        f = filtered(client, pid, include_ids=include, top_k=20)
        exp = [x for x in ids if x in set(include)][:20]
        exp_sc = [s for x, s in zip(ids, sc) if x in set(include)][:20]
        ok, ties = same_ranking(exp, exp_sc, f["product_ids"], f["scores"])
        report("C3", f"include de {len(include)} ids == ranking completo filtrado",
               ok and f["eligible_count"] == len(include) and f["unknown_ids"] == 0,
               f"eligible={f['eligible_count']} unknown={f['unknown_ids']}")

        f = filtered(client, pid, exclude_ids=ids[:30], top_k=50)
        ok, ties = same_ranking(ids[30:80], sc[30:80], f["product_ids"], f["scores"])
        report("C4", "solo exclusiones: los 30 primeros desaparecen y el resto conserva el orden", ok)

        f = filtered(client, pid, include_ids=[ids[0]], exclude_ids=[ids[0]], top_k=5)
        report("C6", "nada elegible -> anchor_found=true y lista vacia",
               f["anchor_found"] is True and f["product_ids"] == [] and f["eligible_count"] == 0)

        f = filtered(client, pid, include_ids=[ids[0], "NO_EXISTE_VALIDACION"], top_k=5)
        report("C7", "id desconocido contado en unknown_ids",
               f["unknown_ids"] == 1 and f["product_ids"] == [ids[0]])
        print(f"      latencia search-filtered: {f['latency_ms']} ms | indice: {f['visual_index_size']} productos")

    f = filtered(client, "NO_EXISTE_VALIDACION", include_ids=["x"], top_k=5)
    report("C5", "\nancla desconocida -> anchor_found=false, sin error",
           f["anchor_found"] is False and f["product_ids"] == [])

    print(f"\nRESULTADO: {sum(results)}/{len(results)} comprobaciones OK")
    return 0 if all(results) else 1


def check_c1(client):
    """Solo C1: /search-by-id igual que en el baseline. Para validar un
    redespliegue de la imagen ANTIGUA (sin /search-filtered) con otra
    configuracion, p. ej. la sonda de arranque ampliada (25/10/2026)."""
    if not BASELINE.exists():
        sys.exit(f"ABORTADO: falta {BASELINE}. Ejecuta antes el modo baseline.")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    results = []
    for name, pid in ANCHORS.items():
        ids, sc = by_id(client, pid)
        ok, ties = same_ranking(base[pid]["product_ids"], base[pid]["scores"], ids, sc)
        results.append(ok)
        print(f"  [{'OK ' if ok else 'FALLO'}] C1 {name}: /search-by-id igual que el baseline"
              f"{f' -- {ties} empate(s) reordenado(s)' if ties else ''}")
    print(f"\nRESULTADO: {sum(results)}/{len(results)} comprobaciones OK")
    return 0 if all(results) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("baseline", "c1", "check"):
        print(__doc__)
        sys.exit(2)
    with make_client() as c:
        modo = sys.argv[1]
        sys.exit(baseline(c) if modo == "baseline" else check_c1(c) if modo == "c1" else check(c))
