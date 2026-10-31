# tools/validation -- herramientas de validacion

Scripts que usamos para validar cada paso antes y despues de desplegar.
Hasta el 30/10/2026 vivian solo en `backup_E5_18102026`, fuera del repo
(recomendacion 1 de `RESUMEN_E5_Nivel2_Estado_30102026.md`): si esa carpeta se
perdia, se perdia la forma de validar.

Todos se ejecutan **desde la raiz del repo**. Ninguno lo recoge pytest
(`pytest.ini`: `testpaths = tests`, `python_files = test_*.py`) ni entra en la
imagen del monolito (`Dockerfile.cloudrun` solo copia `src/`, `data/`,
`static/` y `models/`).

| Fichero | Que valida | Toca produccion | Python |
|---|---|---|---|
| `validate_search_filtered.py` | El embedding service en produccion: `/search-by-id` y `/search-filtered` (C1-C7) | Si, solo lectura (token de `gcloud`) | `venv_fase0` del servicio (tiene `httpx`) |
| `baseline_search_by_id.json` | Linea base de `validate_search_filtered.py` | -- | -- |
| `compare_junit.py` | Comparacion diferencial de la suite (antes / despues) | No | Cualquiera (solo biblioteca estandar) |
| `check_retail_test_events.py` | Que la suite no haya dejado eventos falsos en Google Retail API (H-9) | Si, en modo simulacion | venv del monolito |

Los oraculos de equivalencia del monolito no estan aqui: viven en
`tests/characterization/` (`equiv_harness_*.py`).

---

## 1. `validate_search_filtered.py` -- embedding service

Tres modos:

| Modo | Cuando | Que hace |
|---|---|---|
| `baseline` | ANTES de desplegar el servicio | Guarda lo que devuelve hoy `/search-by-id` para 3 anclas (top 200) |
| `check` | DESPUES, en una revision CON `/search-filtered` | C1 (`/search-by-id` no cambio) + C2-C7 (contrato de `/search-filtered`) |
| `c1` | DESPUES, en una revision SIN `/search-filtered` | Solo C1 |

```powershell
.\src\api\services\embedding-service\venv_fase0\Scripts\python.exe tools\validation\validate_search_filtered.py baseline
.\src\api\services\embedding-service\venv_fase0\Scripts\python.exe tools\validation\validate_search_filtered.py check
```

Codigo de salida: 0 si todo OK, 1 si alguna comprobacion falla, 2 si el modo
no es valido. Requiere `gcloud auth login` hecho; la primera llamada puede
tardar (min-instances 0: arranque en frio, timeout de 300 s).

**Sobre la linea base versionada.** La de este repo es del 23/10/2026 13:04
(anclas CARTERAS `9978484031797`, PANTALONES `9978565329205`, AROS
`9978475839797`). Dos consecuencias:

- **Solo es valida mientras el indice FAISS no cambie.** Si se ha
  sincronizado el catalogo desde entonces, C1 fallara aunque el servicio este
  bien. Por eso el procedimiento es: `baseline` justo antes de desplegar,
  `check` justo despues.
- **El modo `baseline` sobrescribe este fichero.** Despues aparecera en
  `git status` como modificado. Es intencionado (el cambio de linea base queda
  visible): commitearlo junto al despliegue que valida, o descartarlo con
  `git restore tools/validation/baseline_search_by_id.json`.

**Empates.** Dos productos con el mismo vector (p. ej. la misma foto) tienen la
misma puntuacion y FAISS puede ordenarlos distinto entre busquedas.
`same_ranking()` lo acepta solo cuando las puntuaciones son iguales, y lo
informa como "empate(s) reordenado(s)": no es un fallo.

## 2. `compare_junit.py` -- suite del monolito, antes / despues

Responde a una sola pregunta: **¿el cambio altero el CONJUNTO de tests que
fallan?** Compara identificadores de test (no mensajes) a partir de los
informes `--junitxml`, nunca de la salida de consola (ver el docstring).

La linea base se toma en un worktree, no con `git stash` (es una pila: ya nos
costo un incidente en el paso 2):

```powershell
# 1. Linea base: el codigo de HEAD, en una carpeta aparte
git worktree add ..\wt_base HEAD
Copy-Item .env ..\wt_base\.env
cd ..\wt_base
python -m pytest --junitxml=$env:TEMP\junit_antes.xml
cd ..\retail-recommender-system

# 2. Con el cambio aplicado
python -m pytest --junitxml=$env:TEMP\junit_despues.xml

# 3. Comparar
python tools\validation\compare_junit.py $env:TEMP\junit_antes.xml $env:TEMP\junit_despues.xml

# 4. Limpiar el worktree
git worktree remove ..\wt_base --force
```

Los XML van a `%TEMP%` para que no acaben en un commit. Codigo de salida: 0 sin
fallos nuevos, 1 con fallos nuevos, 2 si un fichero falta o no es valido.
`test_inference_latency_under_15ms` depende de la maquina: sus cambios se
informan pero no cuentan como regresion.

Referencia (30/10/2026): 749 tests -> 712 passed, 30 failed, 5 errors,
2 skipped. Los fallos son previos (H-2); lo que importa es que no aparezcan
fallos NUEVOS.

## 3. `check_retail_test_events.py` -- eventos falsos en Retail API

Comprueba si el catalogo de Google Retail API contiene eventos
`purchase-complete` de los visitantes `test_currency_0` ... `test_currency_4`,
que la suite enviaba antes del paso 2b (H-9). Sirve como prueba de no
regresion si se tocan los tests que usan Retail API.

```powershell
# Desde la raiz del repo, con el venv del monolito activado
python tools\validation\check_retail_test_events.py
```

**Usa un metodo destructivo en modo simulacion**: `userEvents.purge` con
`force=false` devuelve cuantos eventos borraria, sin borrar ninguno. El script
tiene tres salvaguardas (constante `FORCE = False`, comprobacion al arrancar y
`assert` antes de cada llamada) y filtra siempre por un `visitorId` concreto,
nunca por fecha o tipo de evento, que podrian incluir eventos reales.
**No cambiar `FORCE`.** Lee del `.env` solo `GOOGLE_PROJECT_NUMBER`,
`GOOGLE_LOCATION` y `GOOGLE_CATALOG`, sin tocar `os.environ`.

---

## Lo que NO esta aqui, y por que

- `freeze_prod.txt` (de `backup_E5_18102026`): es el `pip freeze` del que nacio
  `src/api/services/embedding-service/constraints.txt`. Los 95 paquetes y sus
  versiones son identicos (comprobado el 30/10/2026), y `constraints.txt` ya es
  la fuente de verdad versionada. Ademas estaba en UTF-16 (redireccion `>` de
  PowerShell).
- `compare_junit_v1_obsoleto.py`, parches, copias de `handler`/`f08` y logs
  descargados: evidencia de sesiones pasadas, no herramientas. Siguen en
  `backup_E5_18102026`.

## Historial

- 30/10/2026: versionados desde `backup_E5_18102026`. Unico cambio: los
  docstrings de `validate_search_filtered.py` y `check_retail_test_events.py`
  (decian "no commitear" y apuntaban a la carpeta de copias). La logica es
  identica, comprobado por AST sin docstrings y con pyflakes diferencial.
  `compare_junit.py` y `baseline_search_by_id.json` son copias byte a byte.
