"""
compare_junit.py -- compara dos ejecuciones de pytest (antes / despues de un
cambio) a partir de sus informes --junitxml. Herramienta de diagnostico.

POR QUE XML Y NO TEXTO (18/10/2026)
-----------------------------------
El primer intento filtraba la salida de consola con Select-String y produjo
un fichero vacio. Leer texto de consola es fragil: depende de la codificacion,
de los colores ANSI, de -q/-v y de como la shell trata stderr. El informe
JUnit XML de pytest es estructurado y estable: cada test es un <testcase>, y
si fallo contiene un hijo <failure> o <error> (los fallos de RECOLECCION
tambien aparecen como <testcase> con <error>).

QUE RESPONDE
------------
La unica pregunta que importa en una comparacion diferencial: ¿el cambio
alteró el CONJUNTO de tests que fallan? El total de fallos es irrelevante si
ya habia fallos antes. Se comparan IDENTIFICADORES (clase::nombre), nunca
mensajes, porque los mensajes contienen direcciones de memoria que cambian
en cada ejecucion.

USO
---
    python compare_junit.py junit_antes.xml junit_despues.xml
Codigo de salida: 0 si no hay fallos NUEVOS, 1 si los hay, 2 si un fichero
falta o no es valido.
"""
import sys
import xml.etree.ElementTree as ET

# Tests cuyo resultado depende del tiempo de la maquina, no del codigo.
# Si aparecen o desaparecen entre ejecuciones se informa, pero no cuenta
# como regresion.
TIMING_SENSITIVE = ("test_inference_latency_under_15ms",)


def load(path):
    """Devuelve {id_test: estado} con estado en passed/failed/error/skipped."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"ERROR: no se pudo leer {path}: {exc}")
        sys.exit(2)
    results = {}
    for case in root.iter("testcase"):
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("error") is not None:
            state = "error"
        elif case.find("failure") is not None:
            state = "failed"
        elif case.find("skipped") is not None:
            state = "skipped"
        else:
            state = "passed"
        results[test_id] = state
    return results


def bad(results):
    return {t for t, s in results.items() if s in ("failed", "error")}


def summary(name, results):
    counts = {}
    for state in results.values():
        counts[state] = counts.get(state, 0) + 1
    print(f"{name:8}: {len(results)} tests -> {dict(sorted(counts.items()))}")


def is_timing(test_id):
    return any(t in test_id for t in TIMING_SENSITIVE)


def main(path_before, path_after):
    before, after = load(path_before), load(path_after)
    summary("ANTES", before)
    summary("DESPUES", after)

    new_bad = bad(after) - bad(before)      # fallan ahora y antes no
    fixed = bad(before) - bad(after)        # fallaban y ya no
    only_after = sorted(set(after) - set(before))
    only_before = sorted(set(before) - set(after))

    print(f"\nTests que solo existen DESPUES ({len(only_after)}):")
    for t in only_after:
        print(f"  {after[t]:7} {t}")
    print(f"Tests que solo existian ANTES ({len(only_before)}):")
    for t in only_before:
        print(f"  {before[t]:7} {t}")

    real_new = sorted(t for t in new_bad if not is_timing(t))
    print(f"\nFALLOS NUEVOS ({len(real_new)}):")
    for t in real_new:
        print(f"  {after[t]:7} {t}")
    print(f"Fallos que DESAPARECEN ({len(fixed)}):")
    for t in sorted(fixed):
        print(f"  {t}  (antes: {before[t]}, ahora: {after.get(t, 'no existe')})")
    # Cambios de estado que NO son fallos (p. ej. passed -> skipped). Sin esta
    # seccion, un test que deja de ejecutarse seria invisible en el informe
    # (punto ciego detectado el 19/10/2026, paso 2b: un script que "pasaba"
    # pasa a omitido a proposito, y eso debe verse y explicarse).
    other_changes = sorted(
        t for t in set(before) & set(after)
        if before[t] != after[t] and t not in new_bad and t not in fixed
    )
    print(f"Otros cambios de estado ({len(other_changes)}):")
    for t in other_changes:
        print(f"  {before[t]} -> {after[t]}  {t}")

    timing = sorted(t for t in (new_bad | fixed) if is_timing(t))
    if timing:
        print(f"Cambios en tests sensibles al tiempo (no cuentan): {timing}")

    verdict = "SIN REGRESIONES" if not real_new else "HAY FALLOS NUEVOS"
    print(f"\nVEREDICTO: {verdict}")
    return 0 if not real_new else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
