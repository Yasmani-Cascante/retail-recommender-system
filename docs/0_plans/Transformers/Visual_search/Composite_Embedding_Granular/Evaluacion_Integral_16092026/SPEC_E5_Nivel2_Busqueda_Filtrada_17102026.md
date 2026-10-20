# SPEC -- E5 nivel 2: busqueda visual filtrada por el catalogo

**Fecha:** 17/10/2026
**Estado:** DISENO aprobado (opcion 1, busqueda unica). Paso 0 hecho. Paso 2
VALIDADO EN PRODUCCION el 19/10/2026 (commit `b286d25`, revision
`retail-recommender-00329-mlt`; cierre en la seccion 13). Paso 2b (higiene de
tests) VALIDADO el 19/10/2026 (cierre en la seccion 14). Pasos 1, 3 y 4 sin
implementar.
**Gap:** E5 nivel 2 (pendiente A del prompt de continuidad).
**Relacionado:** `DCT_Cierre_Sesion_01102026.md` (addendum A.16 = estado valido),
`BACKLOG_Busqueda_por_Atributos_Color_24072026.md` (ver seccion 10).

Convencion de evidencia en todo el documento:
**[V]** verificado leyendo el codigo, midiendo o consultando Shopify el 17/10/2026.
**[H]** hipotesis pendiente de confirmar, con el paso que la confirma.

---

## 1. Problema y decision

Hoy las rutas de similitud piden `top_k` vecinos globales a FAISS y filtran
DESPUES (categoria, ya vistos, ancla). En categorias pequenas o sesiones largas
el presupuesto se gasta en tipos ajenos o en productos ya descartados, y el
usuario deja de ver productos que existen (evidencia del 05/10 y 07/10, ver A.11).
El nivel 1 (06/10) agranda el pool; no elimina la causa.

**Decision (17/10/2026):** filtrar DENTRO de la busqueda. El monolito resuelve
el conjunto de productos admitidos con su propio catalogo y lo envia al
embedding service, que busca solo sobre ese subconjunto con un `IDSelector`
de FAISS.

Tres principios que fijan el diseno:

1. **Una sola busqueda filtrada** sobre `(familia + alternativas) - vistos - ancla`.
   Preserva la semantica actual: el resultado es exactamente lo que hoy daria
   un pool infinito (propiedad P2, seccion 3). Presupuestos separados para
   principal y alternativas quedan como refinamiento posterior, medido.
2. **Primitiva general, no un filtro de F-08:** `buscar(fuente_de_consulta, filtro)`.
   El color (sprint posterior) es el segundo consumidor de la misma primitiva.
3. **El servicio no conoce la taxonomia** (principio de Fase 1b). Recibe ids;
   la semantica del catalogo (tipo, y despues color) vive solo en el monolito.

Descartadas (detalle en la conversacion del 17/10): pedir el indice entero
(no escala, ~117 KB por turno), guardar `product_type` en el servicio (segunda
fuente de verdad, obliga a reindexar), sub-indices por categoria (estado extra
sin beneficio a esta escala). NumPy sobre el subconjunto queda como plan B si la
version de faiss desplegada no tuviera selectores.

---

## 2. Hechos verificados que condicionan el diseno

| # | Hecho | Donde |
|---|---|---|
| F1 | [V] El indice es `IndexFlatIP` sin `add_with_ids`: el id interno de FAISS es la posicion en `_id_map`. | `visual_retriever.py`, `_build_faiss` y `_add_to_faiss` |
| F2 | [V] `_category_map` guarda el outfit slot (`accessory`, `dress`...), mas grueso que `SIMILARITY_FAMILIES`. No sirve para este filtro. | `visual_retriever.py`, `SHOPIFY_TYPE_TO_OUTFIT_CATEGORY` |
| F3 | [V] La ruta outfit TAMBIEN filtra despues (`search_pool=150`). El comentario de nivel 1 que dice que "ya lo hace" es inexacto: corregirlo al tocar el fichero. | `visual_retriever.py` ~1160 y 1286; `f08_similarity_resolution.py` comentario NIVEL 1 |
| F4 | [V] `filter_visual_candidates` es un predicado puro por elemento: no depende de la similitud. | `f08_similarity_resolution.py` ~628 |
| F5 | [V] `pool_cats` depende de query, `all_products`, contexto y taxonomia, NO de los resultados visuales. Todos sus ingredientes existen ya en el punto de la busqueda. | handler: F-08C busqueda ~1876, pool_cats ~2028-2090; Fase A busqueda ~2829, pool_cats ~2996-3020 |
| F6 | [V] El calculo de `pool_cats` esta DUPLICADO en las dos rutas, con diferencias minimas. | mismas lineas |
| F7 | [V] **Rama vacia:** hoy el bloque de contrato solo se ejecuta si `visual_ids` no esta vacio (`if _c08_visual_ids and ...` ~1916, `if _f08_visual_ids:` ~2889). Si hay vecinos pero ninguno pasa el filtro, se entra y se recorre el "camino vacio" (catalogo + contrato `exhausted`). | handler |
| F8 | [V] El cliente devuelve `None` = fallo/circuito abierto y `[]` = ancla no indexada. | `colbert_client.py` ~462-550 |
| F9 | [V] `faiss-cpu>=1.7.4` sin fijar en `requirements.txt`; la imagen se construye con `docker build` local (`deploy.sh`). Version en la imagen local: **1.15.1** (paso 0, 17/10). [H] Que la imagen local sea la desplegada: comparar digests en el paso 1. | embedding-service |
| F10 | [V] `search_by_product_id` resuelve la posicion con `self._id_map.index(pid)` (recorrido lineal). | `visual_retriever.py` ~920 |
| F11 | [V] `_id_map` se reasigna en 2 sitios (carga desde disco, indexacion completa) y se extiende en 1 (incremental). | `_load_local_index`, `_run_indexation`, `_add_to_faiss` |
| F12 | [V] Ids de turnos: la ruta principal normaliza a `str` (`conversation_state_manager.py` ~784, campo `List[str]`). [H] Las rutas ~597 y ~887 toman ids del metadata sin normalizar. | `conversation_state_manager.py` |
| F13 | [V] **Alcance real del oraculo `equiv_harness_f08.py`:** compara el modulo extraido contra la logica inline del 02/10, recibiendo `visual_ids` ya hechos. NO modela `pool_cats` (10/10) ni lo que devuelve FAISS. Correccion a lo afirmado el 17/10: por si solo NO protege el nivel 2; hacen falta los oraculos de la seccion 8. | `tests/characterization/equiv_harness_f08.py` |

Mediciones (faiss 1.15.1, vectores sinteticos 3.056 x 768 normalizados; la
latencia de un indice plano depende solo de n, d y k):

| | Hoy (k=100, sin filtro) | Filtrada, 6 ids | Filtrada, 73 ids | Filtrada, 524 ids |
|---|---|---|---|---|
| Latencia | 0,41 ms | 0,02 ms | 0,04 ms | 0,12 ms |
| Exacta frente a "ordenar todo y filtrar" | -- | si | si | si |

Escala (subconjunto del 17%, proporcion actual de AROS): peticion de 8,6 KB con
3.056 productos, 85 KB con 30.000, 282 KB con 100.000. Umbral orientativo para
replantear el transporte (seccion 11): 20.000-30.000 productos.

---

## 3. Fundamento: por que el filtro se puede adelantar

Sea `L` el ranking completo del indice respecto al ancla. Hoy:

```
resultado_hoy(top_k) = filter_visual_candidates(L[:top_k], ancla, cats, type_of, vistos)
```

Nivel 2:

```
F = build_visual_filter(catalogo, cats, ancla, vistos)
resultado_n2(k)      = [p for p in L if F.admits(p)][:k]     # lo que hace FAISS con IDSelector
```

Propiedades, probadas el 17/10 contra la funcion REAL `filter_visual_candidates`
en 20.000 casos aleatorios (catalogo con tipos en minusculas y vacios, ids en
FAISS que el catalogo no conoce, ancla dentro del pool, categorias vacias):

- **P1 (por elemento):** `filter_visual_candidates(L, ...) == [p for p in L if F.admits(p)]`. 0 fallos.
- **P2 (pool infinito):** `resultado_n2(k) == filter_visual_candidates(L, ...)[:k]`. 0 fallos.
- **P3 (prefijo):** `resultado_hoy(top_k)` es prefijo de `resultado_n2(k)`. 0 fallos.
  Consecuencia: el nivel 2 nunca quita nada de lo que hoy se muestra; solo
  anade lo que hoy se perdia por el recorte.

Dos reglas de construccion de `F` que P1 obliga a respetar:

- **Categorias vacias -> `include = None` (sin restriccion), NO "todo el catalogo".**
  Hoy, con `cats` vacia, sobrevive un pid que esta en FAISS aunque no este en el
  `id_index`. Enumerar el catalogo lo excluiria y romperia P1.
- **Comparacion de tipo en mayusculas por ambos lados**, como hace hoy el filtro.

Diferencia deliberada y documentada: el nivel 2 normaliza a `str` los ids
excluidos. Si `shown_products` contuviera enteros (F12, improbable), hoy NO se
excluirian (defecto latente) y con nivel 2 si. Es una correccion, no una regresion.

---

## 4. Contrato de la primitiva

### 4.1 Filtro (monolito -> servicio)

```
VisualFilter
  include : Optional[FrozenSet[str]]   # None = sin restriccion de tipo
  exclude : FrozenSet[str]             # vistos + ancla, ya normalizados a str
  admits(pid) -> bool                  # misma semantica que filter_visual_candidates
```

### 4.2 Fuentes de consulta

| Fuente | Este sprint | Notas |
|---|---|---|
| `product_id` | si | equivale a `/search-by-id` |
| `product_id + boost_text + alpha` | si | equivale a `/search-by-id-with-text-boost` |
| `text` (solo texto) | NO, reservado | lo necesitara el color fase 2 (ordenar "vestidos cortos azules" por relevancia) |
| imagen | NO | el fallback CDN de Fase A (ancla no indexada) sigue con nivel 1. Ruta rara; limitacion documentada |

### 4.3 Respuesta (servicio -> monolito)

```
product_ids     : List[str]
scores          : List[float]     # coseno real, alineado 1:1
anchor_found    : bool            # el ancla esta en el indice
eligible_count  : int             # |admitidos presentes en el indice|
unknown_ids     : int             # ids de include que el indice no conoce (observabilidad)
latency_ms, visual_index_size
```

**`anchor_found` es la pieza que cierra la rama vacia (F7).** Hoy `[]` significa
"ancla no indexada". Con filtro, `[]` puede significar tambien "no queda nada
elegible", y son situaciones opuestas: la primera debe caer al fallback, la
segunda debe recorrer el camino vacio y construir el contrato con `exhausted`.

---

## 5. Cambios en el embedding service

Todos ADITIVOS: ningun endpoint existente cambia de comportamiento.

### 5.1 `visual_retriever.py`

1. **Mapa `id -> posicion` con cache invalidable.** En vez de mantener un dict
   paralelo que habria que actualizar en los tres sitios de F11 (y olvidar uno
   seria un bug silencioso), un metodo `_position_index()` lo reconstruye cuando
   cambia la identidad o la longitud de `_id_map`. Conserva la PRIMERA aparicion
   de cada id, igual que `list.index()`, para no alterar la semantica en indices
   antiguos con duplicados.
2. **`_composite_query(pos, boost_text, alpha)`**: extraer la construccion del
   vector compuesto de `search_by_product_id_with_text_boost`, sin cambio de
   comportamiento, para que la busqueda filtrada la reutilice en vez de copiarla.
   Verificacion: resultados identicos antes y despues (seccion 8.1).
3. **`_build_selector(include_pos, exclude_pos)`**:
   - include presente: `IDSelectorBatch(include - exclude)`.
   - include None y exclude no vacio: `IDSelectorNot(IDSelectorBatch(exclude))`.
   - ambos vacios: sin selector (busqueda normal).
4. **`search_filtered(product_id, include, exclude, top_k, boost_text=None, alpha=0.5)`**
   devuelve pares `(pid, score)` + `anchor_found` + `eligible_count` + `unknown_ids`.
   El ancla se excluye siempre via selector (no con el `top_k + 1` actual).
5. Corregir el comentario de F3 cuando se toque el fichero.

### 5.2 `main.py`

`POST /v1/embed/search-filtered` con cuerpo JSON (una lista de ids no cabe en
query params). Guardas: `top_k` acotado al tamano del indice; tamano maximo de
`include`/`exclude` para proteger el servicio; 503 si el indice no esta listo
(mismo patron que los demas endpoints).

### 5.3 `requirements.txt`

Fijar `faiss-cpu==1.15.1`, la version **leida de la imagen** en el paso 0 (no
una supuesta), tras confirmar en el paso 1 que la imagen local es la
desplegada. Mismo motivo que el incidente de `anthropic`. Coincide con la
version usada en las mediciones de la seccion 2.

---

## 6. Cambios en el monolito

### 6.1 `f08_similarity_resolution.py`

1. **`build_pool_request(...)`** -- funcion pura que reemplaza el calculo
   duplicado de `intent`, `requested_ordered`, `alt_types` y `pool_cats` (F6).
   Paso de refactor SIN cambio de comportamiento, protegido por el oraculo 8.3.
2. **`VisualFilter` + `build_visual_filter(id_index, categories, anchor_pid, exclude_ids)`**
   con las dos reglas de la seccion 3. Prototipo validado en la prueba P1-P3.
   **Extension prevista para color (no en este sprint):** un argumento opcional
   adicional; con `None` no cambia nada. Se anade cuando el censo (seccion 10)
   confirme la calidad del dato, para no escribir codigo sin consumidor.
3. **Flag `RECS_VISUAL_FILTER_IN_SEARCH`** (default `0`), mismo patron defensivo
   que `principal_first_enabled()`.

### 6.2 `colbert_client.py`

`search_filtered(...)` -> `FilteredVisualResult | None`. `None` mantiene la
semantica de fallo de F8 y pasa por el mismo circuit breaker. Envia `exclude`
siempre e `include` solo si no es None.

### 6.3 `mcp_conversation_handler.py` (Fase A y F-08C, simetricos)

1. Calcular la peticion de pool con `build_pool_request` ANTES de la busqueda y
   reutilizar su resultado dentro del bloque (se elimina la duplicacion).
2. Con flag activo: `F = build_visual_filter(...)` con el MISMO criterio que el
   filtro de hoy (`pool_cats or expanded_cats` en A, `pool_cats or query_cats` en C)
   y llamar a `search_filtered`. Con flag inactivo: el camino actual intacto.
3. **Condicion de entrada al bloque (F7):** con flag activo, entrar si
   `anchor_found` es True aunque no haya resultados. Sin esto, la rama vacia
   saltaria el contrato. Es la tercera aparicion potencial del patron
   "`if hay_algo:` con rama vacia" (leccion 3).
4. **El filtro de la etapa 2 se conserva** como defensa. Con nivel 2 debe no
   eliminar nada; si elimina algo se registra un warning con el recuento: es una
   divergencia entre el catalogo usado para construir `F` y el usado para filtrar.
5. `top_k` sin cambios (`visual_pool_size`). Con filtro el nivel 1 deja de ser
   necesario, pero mantenerlo minimiza el cambio y no cuesta nada.
6. **Cambio semantico documentado:** `visual_rank` pasa de "posicion en el
   vecindario completo" a "posicion entre los elegibles". El `% match` usa
   `score`, no el rango. [H] El rango solo es informativo: confirmar con grep de
   sus consumidores antes de implementar.
7. Logs nuevos (stdlib logging con f-strings en `src/api/core/`, ver learnings):
   `E5 filtro: include=N exclude=M eligible=E devueltos=R anchor_found=B` y el
   warning del punto 4.

---

## 7. Lo que NO cambia

Rutas F-08B (outfit) y Estandar; `_category_map` y la busqueda de outfit; los
endpoints existentes del servicio; el contrato `RecommendationSet`; G1 (catalogo
antes que relleno); los textos de steering y alphas.

---

## 8. Red de seguridad

### 8.1 Servicio (tests unitarios nuevos)

- Exactitud: para include/exclude/None aleatorios, `search_filtered(k)` ==
  ordenar el indice entero y filtrar despues, `[:k]`. Incluye k > elegibles,
  ids desconocidos, ancla en include, duplicados en `_id_map`.
- `_composite_query`: salida identica a la del metodo actual antes del refactor.
- `_position_index`: se invalida tras carga, indexacion completa e incremental.

### 8.2 Monolito -- oraculo P1/P2/P3 (nuevo, persistente)

Convertir el prototipo del 17/10 en `tests/characterization/equiv_harness_e5.py`,
en el repo (NO en `/tmp`: los oraculos de mutacion anteriores se perdieron asi).
Importa el modulo real y comprueba P1, P2 y P3 con la semilla fija.

### 8.3 Monolito -- equivalencia de `build_pool_request` (HECHO, 17/10/2026)

`tests/characterization/equiv_harness_pool_request.py`: copias literales de
los dos bloques inline de `pool_cats` (Fase A y F-08C) comparadas con la
funcion extraida. Resultado: 20.000 casos por ruta, 0 divergencias, las 7
combinaciones ruta/source/intent cubiertas, 8/8 mutantes detectados (la
auto-verificacion por mutantes va dentro del propio fichero).

**Desviacion consciente:** la spec decia "ampliar el oraculo" existente. Se
creo un fichero propio para no alterar la salida de `equiv_harness_f08.py`,
referencia historica del 02/10 cuyos recuentos cita el DCT. El motivo esta
tambien en la cabecera del oraculo nuevo.

### 8.4 Rama vacia (test dirigido)

`anchor_found=True` con 0 resultados -> se entra al bloque, se recorre el camino
vacio y el contrato sale con `exhausted` respaldado. Y `anchor_found=False` ->
fallback como hoy.

### 8.5 Existentes

`equiv_harness_f08.py` (40.000) en verde antes y despues.

**Correccion (18/10/2026):** la cifra "228 tests" del prompt de continuidad no
corresponde a `tests/unit`, que recoge 723 tests con 36-37 fallos y 5 errores
PREVIOS y ajenos a E5 (seccion 13.4, H-2). Con fallos previos, "en verde" no es
un criterio util. El criterio es DIFERENCIAL: ejecutar la suite con y sin el
cambio, guardar cada resultado con `--junitxml` y comparar los CONJUNTOS de
fallos por identificador (nunca por mensaje: contienen direcciones de memoria).
Herramienta: `compare_junit.py` (fuera del repo por ahora; ver 13.5).
Veredicto exigido: 0 fallos nuevos y 0 fallos que desaparezcan sin explicacion.

---

## 9. Plan de despliegue (un cambio cada vez, con validacion)

| Paso | Que | Validacion |
|---|---|---|
| 0 | Leer la version de faiss de la imagen: `docker run --rm gcr.io/retail-recommendations-449216/retail-embedding-service pip show faiss-cpu` | **HECHO 17/10: faiss-cpu 1.15.1.** Pendiente: confirmar en el paso 1 que el digest local coincide con el desplegado |
| 1 | Servicio: 5.1-5.3. Desplegar | `curl.exe` a `/search-filtered` sin filtro == `/search-by-id`; con filtro, exactitud en 3 anclas reales (CHAQUETAS, CARTERAS, AROS) |
| 2 | Monolito: solo `build_pool_request` (refactor). **VALIDADO EN PRODUCCION 19/10** -- commit `b286d25`, revision `00329-mlt`. Evidencia completa en la seccion 13 | oraculo 8.3 + logs de produccion identicos a los actuales |
| 2b | Higiene de tests (prerequisito del 3): cortar la fuga de `.env` hacia toda la sesion de pytest y aislar `TestTamanoDelPoolVisual` del entorno (13.4, H-1). **VALIDADO 19/10** (seccion 14) | comparacion diferencial: los 6 fallos de `TestTamanoDelPoolVisual` desaparecen y no aparece ningun fallo nuevo |
| 3 | Monolito: filtro + cliente + entrada al bloque, flag `0`. Desplegar | sin cambios observables con flag apagado |
| 4 | Flag `1` en produccion | logs `E5 filtro`, warning defensivo = 0, sesiones reales de las anclas del 05/10 y 07/10 |

**Metricas antes/despues** (de Cloud Logging, misma ventana): proporcion de
turnos con principal completo, frecuencia de `exhausted`, frecuencia de caida a
fallback generico, y `supervivientes / top_k` por categoria (deberia tender a 1).

**Rollback:** `RECS_VISUAL_FILTER_IN_SEARCH=0`, sin redeploy.

---

## 10. Relacion con la busqueda por color

Verificado en Shopify el 17/10 (consulta GraphQL de solo lectura, 55 productos de
VESTIDOS CORTOS, VESTIDOS LARGOS, ZAPATOS, AROS y CARTERAS):

- [V] 55/55 tienen la opcion `COLOR` con un unico valor, vocabulario de familias
  en mayusculas (AZUL, VERDE, ROJO, NEGRO, DORADO, BURDEO, CAFE...). No es
  metafield.
- [V] 3/55 contradicen el titulo: Kika Rosado Intenso -> NARANJO, Kika Fucsia ->
  NARANJO, Tenerife Rojo -> NEGRO. Ademas 2/25 VESTIDOS CORTOS se titulan
  "Vestido Largo" (error de `product_type`). Muestra pequena y no aleatoria: no
  extrapolar el porcentaje.
- [V] Hoy la ruta Estandar elige dentro de la categoria con `random.sample`; el
  color no existe en el handler.
- [H fuerte] `options` llega al `id_index`: `get_products` pide `/products.json`
  sin `fields=` y `_normalize_product_price` conserva todos los campos. Lo
  confirma la primera salida del censo.

Lo que aporta este diseno al color: tipo y color se convierten en restricciones
DURAS resueltas por el catalogo, y el embedding solo ordena. Eso elimina la
mezcla de tres senales del backlog (3.4) en el caso principal y deja la
calibracion de alpha (3.2) solo para matices sin dato estructurado.

**Censo de COLOR (pre-requisito del sprint de color, solo lectura, puede
correr en paralelo a E5):** recorrer el catalogo que carga el monolito y emitir
(a) % de productos con `options` y con `COLOR`; (b) valores distintos con
recuento; (c) productos con mas de un valor; (d) contradicciones titulo/COLOR
con un lexico de colores del titulo; (e) contradicciones titulo/`product_type`
por largo. Salida CSV para limpieza en Shopify Admin.

---

## 11. Riesgos y limites conocidos

- **Escalabilidad del transporte:** la peticion crece con el subconjunto. Por
  encima de ~20.000-30.000 productos, o con tenants SaaS grandes, mover los
  atributos junto a los vectores (camino natural: pgvector en Supabase, cuya
  0.8.0 anadio iterative index scans para el filtrado). La interfaz
  `buscar(fuente, filtro)` en el monolito permite migrar sin tocar las rutas.
- **Desfase catalogo / indice:** un producto re-etiquetado en Shopify cambia en
  el monolito al resincronizar TF-IDF; el indice no necesita saberlo (ventaja de
  la opcion 1). Un producto nuevo no indexado sigue sin aparecer, igual que hoy.
- **Fallback CDN de Fase A** sin filtro (4.2).
- **Despliegue cruzado:** si el monolito llamara a `/search-filtered` antes de
  que exista, cada 404 contaria como fallo del circuit breaker visual. Mitigado
  por el orden servicio -> monolito y el flag apagado por defecto.

---

## 12. Estimacion

1,5-2 sesiones: servicio ~0,5; monolito ~0,75 (la mayor parte, reordenar dos
rutas y la rama vacia); oraculos y tests ~0,5; despliegue y validacion aparte.

---

## 13. Cierre del paso 2 (19/10/2026)

### 13.1 Que se entrego

Commit `b286d25` en `feature/visual_search` (5 ficheros, +1048 -48), subido a
GitHub el 19/10. Desplegado como `retail-recommender-00329-mlt` el 18/10.

| Fichero | Cambio |
|---|---|
| `src/recommenders/f08_similarity_resolution.py` | `PoolRequest` + `build_pool_request()`; docstring de dependencias corregido |
| `src/api/core/mcp_conversation_handler.py` | las dos copias inline (Fase A y F-08C) sustituidas por una llamada cada una |
| `tests/unit/test_f08_similarity_resolution.py` | +7 tests `TestBuildPoolRequest` |
| `tests/characterization/equiv_harness_pool_request.py` | oraculo nuevo con auto-verificacion por mutantes |
| esta spec | creada |

### 13.2 Evidencia

| Capa | Resultado |
|---|---|
| Codigo | Oraculo 8.3: 40.000 casos, 0 divergencias, 7 combinaciones ruta/source/intent cubiertas, 8/8 mutantes detectados. Oraculo 02/10 sin cambios. pyflakes diferencial: 0 avisos nuevos |
| Integridad | Ficheros del repo verificados por hash contra la version validada; tras la recuperacion de git (13.5), `git diff` identico byte a byte al parche de respaldo |
| Suite | Comparacion diferencial por `--junitxml`: 716 tests comunes con el MISMO resultado, 0 fallos nuevos, 0 que desaparecen, 7 tests nuevos en `passed` |
| Produccion | Linea base `00328-44n` (18/10) frente a `00329-mlt` (18-19/10), mismo script de extraccion para ambas |

Turnos comparados en produccion (campos `reparto`, `contrato`, `pool admite`,
`category expansion`):

| Turno | Ancla | Ruta / rama | Resultado |
|---|---|---|---|
| B-1 | `palazzo-silvia-negro` | Fase A / exact_type | identico caracter a caracter, recuentos incluidos |
| B-2 | `palazzo-ariel-satin-verde-oscuro` | F-08C / exact_type, camino vacio | identico |
| C-1 | `aros-alana-multicolor-rosado` | Fase A / parent_group | identico |
| C-2 | `aros-alba-piedras-colgante-rose-gold` | F-08C / query_text (8 categorias) | identico |
| D-1 | `vestido-corto-amparo-champagne` | Fase A / parent_group nupcial | identico |
| A-2 (x2) | anclas CARTERAS | F-08C / parent_group | linea `pool admite` identica en las dos apariciones; familia G2 `['CARTERAS', 'CLUTCH']` identica |
| A-4 | otra ancla AROS | F-08C / query_text | `pedido`, `intent`, `contrato` identicos (`en_pool` 123 -> 124: ancla distinta y relleno aleatorio previo) |
| extra | `maxi-falda-pascuala-...` (FALDAS) | F-08C / exact_type | conforme a la prediccion del codigo real |

Los mensajes de B-1, B-2 y D-1 se escribieron en otro idioma o con otra frase y
el resultado fue identico: en estas rutas decide el ancla, no el texto.

### 13.3 Hueco residual (aceptado)

La combinacion **Fase A x ancla CARTERAS** (A-1) no se ejercito: la ejecucion
del 19/10 reutilizo la sesion del 18/10 (`LOADED existing MCP context ... with 4
turns`) y los turnos de bolsos pasaron por F-08C. Se acepta sin repetir porque:
(a) `build_pool_request` es pura y no depende de la ruta; para CARTERAS sin
texto ambas rutas resuelven `parent_group` con la misma entrada; (b) esa misma
llamada dio resultado identico en F-08C; (c) el cableado de Fase A esta
validado con tres anclas que cubren sus dos ramas y no distingue por tipo;
(d) el oraculo cubre la combinacion.

### 13.4 Hallazgos fuera de alcance

| Id | Hallazgo | Estado |
|---|---|---|
| H-1 | **Fuga de entorno en tests.** `tests/unit/test_currency_validation.py` linea 18 llama a `load_dotenv()` a nivel de modulo: se ejecuta en la RECOLECCION y carga el `.env` de la raiz (incluido `RECS_VISUAL_POOL_BASE=100`) para toda la sesion. Por eso los 6 tests de `TestTamanoDelPoolVisual` fallan en la suite completa y pasan aislados. Ademas `tests/unit/test_config.py` vacia todo `os.environ` (lineas 31, 40, 85, 94, 123) y lo restaura. Diagnosticado el 18/10 con un espia sobre `os.environ.__setitem__/__delitem__` | **resuelto en el paso 2b** (seccion 14). Los `os.environ.clear()` de `test_config.py` siguen: restauran el entorno y hoy no causan fallos |
| H-2 | `tests/unit` tiene 36-37 fallos y 5 errores previos, ajenos a E5 (tests desfasados: `factories.get_settings`, `ShopifyKBSyncService._use_content_versioning`, mocks asincronos de `market_context_manager`...). `test_inference_latency_under_15ms` (MiniLM) depende del tiempo de la maquina | pendiente |
| H-3 | `src/api/_health_patch.py` no es analizable por coverage (`couldnt-parse`) | pendiente de revisar si produccion lo importa |
| H-4 | Stash antiguo `feature/phase1-extend-servicefactory` ("Creada infraestructura de FastAPI Dependency Injection") sigue en la pila | revisar y decidir |
| H-5 | **Caso de referencia del camino vacio:** sesion B, turno 2 (`palazzo-silvia-negro` y despues `palazzo-ariel-satin-verde-oscuro`) produce `principal=0[] alternatives=8['FALDAS'] exhausted=True`. Debe mantenerse identico en los pasos 3 y 4 (hallazgo F7) | usar en 3/4 |
| H-6 | El 404 de OpenRouter (LFM2) sigue activo: cada llamada al LLM pierde 0,4-1,2 s antes del fallback | pendiente (final) |
| H-7 | Los logs van en `jsonPayload.event`, no en `textPayload`: las consultas `gcloud logging read` deben filtrar por `jsonPayload.event` y usar `--format=json` | aplicado |
| H-8 | El unico producto `CLUTCH` de la tienda (CLUTCH LEONOR) esta ARCHIVADO: hoy la familia G2 de CARTERAS no aporta productos CLUTCH | informativo |
| H-9 | **Escrituras reales en Google Retail API desde la suite unitaria.** `test_currency_validation.py` (un script manual con forma de test, sin asserts) se ejecutaba en cada pase de pytest (`asyncio_mode = auto`) y, con `GOOGLE_PROJECT_NUMBER` en `.env` y credenciales ADC en la maquina (ambas confirmadas el 19/10), llamaba a `UserEventServiceClient.write_user_event` con 5 eventos `purchase-complete` FALSOS (visitantes `test_currency_0..4`). Duracion medida del test: 3,6 s (mediana del resto: 0,004 s) | escrituras cortadas en el paso 2b; pendiente comprobar el catalogo en modo solo lectura (14.3) |

### 13.5 Lecciones de proceso

1. **Validar contra la lista de turnos ESPERADOS, no contra los que aparecen.**
   Una descarga de logs empezo a mitad de sesion y omitio A-1/A-2; otra
   ejecucion reutilizo una sesion antigua. Ambas cosas solo se detectaron
   porque el extractor marca los turnos truncados y se comprueba la
   precondicion (turno 1 real) en la propia evidencia.
2. **Consumir salidas estructuradas.** Filtrar la consola con `Select-String`
   produjo un fichero vacio en silencio; `--junitxml` resolvio la comparacion.
3. **`git stash` es una pila.** Un segundo `pop` saco un stash antiguo y dejo
   conflictos (`dependencies.py` con marcas `<<<<<<<`: codigo invalido). Se
   recupero sin perdidas probando antes la secuencia en un repositorio de
   laboratorio. Para comparaciones antes/despues se usa en su lugar: copiar
   fuera del repo -> verificar por hash -> `git restore` -> ejecutar -> copiar
   de vuelta -> verificar por hash.
4. **Verificar antes de destruir:** comprobar que lo que se descarta esta
   guardado (stash, copia por hash) antes de cada operacion destructiva.
5. **Activar el venv y comprobarlo** (`Get-Command python`): dos ejecuciones
   de pytest fallaron por usar el Python global.
6. **Herramientas de esta ronda** (fuera del repo): `compare_junit.py`
   (comparacion diferencial de suites) y el extractor de turnos de logs. Queda
   por decidir si se incorporan al repo, por ejemplo en `tools/`.

---

## 14. Cierre del paso 2b -- higiene de tests (19/10/2026)

### 14.1 Cambio

| Fichero | Cambio |
|---|---|
| `tests/unit/test_currency_validation.py` | `load_dotenv()` pasa del nivel de modulo al bloque `__main__`; el modulo se marca `skip` (+ `integration`, `google`) para pytest con el motivo visible. Como script manual se comporta igual |
| `tests/unit/test_f08_similarity_resolution.py` | fixture `autouse` en `TestTamanoDelPoolVisual` que borra `RECS_VISUAL_POOL_BASE` y `RECS_VISUAL_POOL_CAP` (mismo patron que los tests de `RECS_PRINCIPAL_FIRST` del fichero) |

Las dos capas son necesarias: la defensa sola arreglaria los 6 tests pero
mantendria la fuga y las escrituras en Retail API; el arreglo de origen solo
no protege frente a variables exportadas en la terminal.

### 14.2 Evidencia

| Capa | Resultado |
|---|---|
| Laboratorio con el `pytest.ini` real | original: 6 fallos + 5 llamadas a Retail API (stub); cambiado: 0 fallos, 1 omitido, 0 llamadas; con variables exportadas: 0 fallos; sonda: el `.env` ya no llega a los tests; uso como script: identico |
| Aplicacion al repo | contenido identico al validado (hash del contenido normalizado); finales de linea uniformes |
| Suite (diferencial `--junitxml`) | 723 tests en ambas: **0 fallos nuevos**; desaparecen exactamente los 6 de `TestTamanoDelPoolVisual`; unico cambio de estado: `test_currency_validation` passed -> skipped. Fallos previos: 36 -> 30 |

Ningun otro test dependia en silencio de las variables que filtraba el `.env`
(era el riesgo vigilado: el espia solo registraba la familia `RECS_*`).

### 14.3 Pendiente: eventos falsos en el catalogo (H-9)

Comprobacion de SOLO LECTURA con `check_retail_test_events.py` (fuera del
repo): llama a `userEvents.purge` con `force=false`, que segun la referencia
oficial devuelve el numero de eventos que se borrarian sin borrar ninguno.
Salvaguardas: constante `FORCE = False` que el script se niega a ejecutar si
se altera, `assert` por peticion, filtro por `visitorId` concreto (nunca por
tiempo o tipo, que incluirian eventos reales), y el mismo catalogo que el
script original. Probado con un cliente simulado, incluida la mutacion
`FORCE = True` (0 peticiones enviadas). La limpieza, si hiciera falta, sera
una decision aparte.

### 14.4 Lecciones

1. **Un test sin asserts no es un test**, y uno que escribe en un servicio
   externo no pertenece a la suite unitaria.
2. **Los efectos a nivel de modulo en ficheros de test afectan a toda la
   sesion**: pytest importa todos los ficheros en la recoleccion, antes de
   ejecutar ninguno.
3. **Medir los finales de linea con Python**, no con `grep -c $'\r$'`: el
   `sh` del entorno de analisis no interpreta esa sintaxis y los recuentos
   eran invalidos. Para verificar ficheros entre maquinas, comparar el hash
   del contenido normalizado y comprobar que los finales de linea son
   uniformes.
4. **Una herramienta de comparacion tambien puede tener puntos ciegos**:
   `compare_junit.py` no informaba de cambios `passed -> skipped`; se amplio
   antes de usarla en este paso.
