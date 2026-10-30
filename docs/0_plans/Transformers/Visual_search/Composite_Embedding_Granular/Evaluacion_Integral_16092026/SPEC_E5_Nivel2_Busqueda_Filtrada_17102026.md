# SPEC -- E5 nivel 2: busqueda visual filtrada por el catalogo

**Fecha:** 17/10/2026
**Estado:** DISENO aprobado (opcion 1, busqueda unica). Paso 0 hecho. Paso 2
VALIDADO EN PRODUCCION el 19/10/2026 (commit `b286d25`, revision
`retail-recommender-00329-mlt`; cierre en la seccion 13). Paso 2b (higiene de
tests) VALIDADO el 19/10/2026 (cierre en la seccion 14). Paso 1 (endpoint
`/v1/embed/search-filtered`) VALIDADO EN PRODUCCION el 26/10/2026 (revision
`retail-embedding-service-00062-kvd`; cierre en la seccion 15). Paso 3 (filtro
en el monolito, flag apagado) VALIDADO EN PRODUCCION el 29/10/2026 (revision
`retail-recommender-00330-vwb`; cierre en la seccion 16). Paso 4 (flag
activado) VALIDADO EN PRODUCCION el 29/10/2026 (revision
`retail-recommender-00332-d87`; cierre en la seccion 17). Queda el seguimiento
con trafico real (17.5).
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
| 0 | Leer la version de faiss de la imagen: `docker run --rm gcr.io/retail-recommendations-449216/retail-embedding-service pip show faiss-cpu` | **HECHO 17/10: faiss-cpu 1.15.1.** Confirmado el 21/10 directamente sobre la imagen DESPLEGADA (`pip show` sobre su digest `sha256:4a5185404e96...`) |
| 1 | Servicio: 5.1-5.3. Desplegar. **VALIDADO EN PRODUCCION 26/10** -- revision `00062-kvd`, imagen `sha256:63df725e...`. Evidencia en la seccion 15 | `validate_search_filtered.py check`: 19/19 (incluye `/search-by-id` identico al baseline previo al despliegue) |
| 2 | Monolito: solo `build_pool_request` (refactor). **VALIDADO EN PRODUCCION 19/10** -- commit `b286d25`, revision `00329-mlt`. Evidencia completa en la seccion 13 | oraculo 8.3 + logs de produccion identicos a los actuales |
| 2b | Higiene de tests (prerequisito del 3): cortar la fuga de `.env` hacia toda la sesion de pytest y aislar `TestTamanoDelPoolVisual` del entorno (13.4, H-1). **VALIDADO 19/10** (seccion 14) | comparacion diferencial: los 6 fallos de `TestTamanoDelPoolVisual` desaparecen y no aparece ningun fallo nuevo |
| 3 | Monolito: filtro + cliente + entrada al bloque, flag `0`. Desplegar. **VALIDADO EN PRODUCCION 29/10** -- revision `00330-vwb` (seccion 16) | sin cambios observables con flag apagado |
| 4 | Flag `1` en produccion. **VALIDADO EN PRODUCCION 29/10** -- revision `00332-d87`, misma imagen que la `00330` (seccion 17) | logs `E5 filtro`, warning defensivo = 0, sesiones reales de las anclas del 05/10 y 07/10 (pendiente: 17.5) |

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
| H-9 | **Escrituras reales en Google Retail API desde la suite unitaria.** `test_currency_validation.py` (un script manual con forma de test, sin asserts) se ejecutaba en cada pase de pytest (`asyncio_mode = auto`) y, con `GOOGLE_PROJECT_NUMBER` en `.env` y credenciales ADC en la maquina (ambas confirmadas el 19/10), llamaba a `UserEventServiceClient.write_user_event` con 5 eventos `purchase-complete` FALSOS (visitantes `test_currency_0..4`). Duracion medida del test: 3,6 s (mediana del resto: 0,004 s) | escrituras cortadas en el paso 2b. **Cerrado 20/10 sin limpieza** (14.4): con las ADC actuales la suite no podia escribir, y las rutas conversacionales de produccion no usan Retail API |
| H-10 | Produccion inicializa el singleton de Retail API al arrancar (`Retail API recommender singleton created`, una vez por instancia), pero ninguno de los 35 mensajes de log de `retail_api.py` (`get_recommendations`/`predict` y `record_user_event`/`write_user_event`) aparece en 4.378 entradas de las revisiones 00328/00329 que recorren todas las rutas conversacionales. Posible dependencia muerta (coste de arranque y credenciales) | pendiente: confirmar si algun endpoint no conversacional la usa |
| H-11 | Las ADC locales son `impersonated_service_account` (configuradas el 29/09/2026) y la suplantacion falla: `iam.serviceAccounts.getAccessToken` denegado. Toda herramienta local que use APIs de Google falla al obtener el token | pendiente (configuracion local) |

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

### 14.4 Resultado de la comprobacion y cierre de H-9 (20/10/2026)

La comprobacion no llego a Retail API: fallo al obtener credenciales
(`Unable to acquire impersonated credentials`, `iam.serviceAccounts.getAccessToken`
denegado). Las ADC son de suplantacion desde el 29/09/2026 (H-11).

H-9 se cierra SIN limpieza del catalogo:

1. El script de moneda usaba las mismas ADC (`UserEventServiceClient()` sin
   parametros), asi que desde el 29/09 sus escrituras fallaban igual (los
   3,6 s medidos encajan con 5 fallos rapidos).
2. Antes del 29/09 no se puede saber sin otras credenciales.
3. Aunque existan eventos falsos, las rutas conversacionales de produccion no
   consultan Retail API (H-10): 0 de 35 mensajes de `retail_api.py` en 4.378
   entradas que cubren Fase A, F-08C, Estandar y los tipos de rama.

Riesgo residual aceptado: el guion no ejercito endpoints no conversacionales.
**Si se reactiva Retail API** para recomendaciones, ejecutar antes
`check_retail_test_events.py` con credenciales validas y limpiar los visitantes
`test_currency_0..4` si aparecen.

Nota del mismo diagnostico: la linea 198 del `.env` local empieza por `*` en
lugar de `#` y python-dotenv no la puede interpretar (la descarta; era un
comentario y no se pierde ninguna variable).

### 14.5 Lecciones

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

---

## 15. Cierre del paso 1 -- endpoint `/search-filtered` (26/10/2026)

### 15.1 Que se entrego

Commit del paso 1 en `feature/visual_search` (mensaje `feat(embedding-service):
busqueda visual filtrada en FAISS (E5 nivel 2 paso 1); imagen sin venv_fase0
(.dockerignore); versiones de produccion fijadas (constraints.txt)`), 9
ficheros en `src/api/services/embedding-service/`:

| Fichero | Cambio |
|---|---|
| `visual_retriever.py` | `FilteredSearchResult`, `_positions()` (cache id -> posicion), `_composite_query()` (extraida sin cambios del text boost), `search_filtered()` |
| `main.py` | `POST /v1/embed/search-filtered` (limites: 20.000 ids, `top_k` 1-10.000, `alpha` 0-1) |
| `requirements.txt` | `faiss-cpu>=1.7.4` -> `==1.15.1` (la de produccion) |
| `Dockerfile` | instala con `-c constraints.txt`; corregido un comentario que citaba torch 2.1.0 (es 2.7.0) |
| `.dockerignore` (nuevo) | lista BLANCA: solo `requirements.txt`, `constraints.txt` y los 3 `.py` |
| `constraints.txt` (nuevo) | las 95 versiones exactas del `pip freeze` de la imagen desplegada |
| `pytest.ini` (nuevo) | raiz de pytest en la carpeta del servicio (sin el, se aplicaba el del monolito) |
| `requirements-test.txt` (nuevo) | entorno de tests con `-c constraints.txt` (no puede desalinearse de produccion) |
| `tests/test_search_filtered.py` (nuevo) | 77 tests |

Configuracion de despliegue: sonda de arranque 16 x 15 s = 240 s (H-15).

### 15.2 Evidencia

| Capa | Resultado |
|---|---|
| Codigo | 77 tests en verde en el laboratorio y en `venv_fase0` (Windows), con las versiones de produccion. Exactitud frente a "busqueda completa filtrada despues" en 50 casos; 15/15 mutantes detectados; pyflakes sin avisos nuevos |
| Codigo desplegado previo | `sha256sum` de `main.py`, `visual_retriever.py` y `colbert_retriever.py` en la imagen de produccion == los del repo (base real del diff) |
| Imagen nueva | `/app` con 5 ficheros, hashes == repo; `pip freeze` == produccion (95 paquetes, 0 diferencias); 3 modelos de HuggingFace con la MISMA revision que produccion; tamano 6,56 GB -> 4,44 GB |
| Imagen subida | `RepoDigests` de la imagen local == digest de la revision desplegada (`sha256:63df725e...`) |
| Produccion | `validate_search_filtered.py check`: 19/19 en 3 anclas reales (CARTERAS `9978484031797`, PANTALONES `9978565329205`, AROS `9978475839797`): `/search-by-id` identico al baseline tomado ANTES de desplegar; endpoint nuevo exacto; ramas vacia, desconocida e ids desconocidos correctas. Latencia 0,5-1,7 ms (5,1 ms la primera llamada) |

### 15.3 Historial de despliegue

| Revision | Imagen | Sonda | Resultado |
|---|---|---|---|
| 00056-2qr | antigua `4a518540...` | 9 x 15 s | en produccion desde el 07/10; fallo 56 de 64 arranques (H-15) |
| 00057, 00058, 00059, 00060 | nueva `63df725e...` | 9 x 15 s | 4 intentos (23-25/10), todos rechazados por la sonda (134-139 s) |
| 00061-f88 | antigua `4a518540...` | **16 x 15 s** | 25/10. Solo cambia la sonda: corrige H-15 sin tocar el codigo. C1 3/3 |
| **00062-kvd** | nueva `63df725e...` | **16 x 15 s** | 26/10. Paso 1 en produccion. 19/19 |

Los dos intentos del 26/10 con el texto literal `<DIGEST>` fueron rechazados
por Cloud Run al validar la peticion (`code 3`), sin crear revision.

Comando de despliegue validado (PowerShell, desde la raiz del repo):
1. `docker build -t gcr.io/retail-recommendations-449216/retail-embedding-service:latest -f src/api/services/embedding-service/Dockerfile src/api/services/embedding-service`
2. `docker push gcr.io/retail-recommendations-449216/retail-embedding-service:latest`
3. Leer el digest subido: `docker image inspect gcr.io/retail-recommendations-449216/retail-embedding-service:latest --format "{{json .RepoDigests}}"`
4. `gcloud beta run deploy retail-embedding-service --image gcr.io/retail-recommendations-449216/retail-embedding-service@sha256:<digest del punto 3> --project retail-recommendations-449216 --region us-central1 --memory 4Gi --cpu 1 --cpu-boost --min-instances 0 --max-instances 1 --timeout 300 --no-allow-unauthenticated --ingress all --startup-probe="httpGet.path=/health/startup-probe,httpGet.port=8080,initialDelaySeconds=10,periodSeconds=15,timeoutSeconds=3,failureThreshold=16" --set-env-vars VISUAL_INDEX_BUCKET=retail-recommendations-449216-visual-index`
5. Comprobar que `status.imageDigest` de la revision nueva == digest del punto 3.

### 15.4 Hallazgos

| Id | Hallazgo | Estado |
|---|---|---|
| H-12 | `deploy.sh`: comentarios que contradicen a los flags (cpu 2 / min-instances 1 frente a cpu 1 / 0), shebang fuera de la primera linea, finales CRLF (bash no los admite), `failureThreshold=9`, despliegue por etiqueta y health check sin autenticacion (siempre rechazado) | **resuelto** el 26/10: `deploy.sh` revisado y aplicado (contenido `076bdbf4...`); hace lo mismo que el despliegue validado (12/12 flags identicos en simulacion; shellcheck sin avisos) |
| H-13 | Carrera latente: la indexacion incremental hace `add()` en el indice mientras otros hilos buscan. La wiki de FAISS exige exclusion mutua para operaciones que modifican el indice; el comentario de `_add_to_faiss` afirma lo contrario. `search_filtered()` no la agrava (misma guarda `0 <= idx`) | pendiente (cambio aparte) |
| H-14 | La imagen en produccion llevaba `venv_fase0` (entorno virtual de Windows, 2,1 GB de 6,56 GB) y ficheros sobrantes, por `COPY . .` sin `.dockerignore` | **resuelto** en el paso 1 |
| H-15 | **Incidente de produccion:** sonda de arranque de ~130 s frente a arranques MEDIDOS de 104-140 s (hasta ~175 s ESTIMADOS para los que la sonda interrumpio: fase ColBERT de hasta 134,9 s + resto). La revision 00056 fallo 56 de 64 arranques en frio (18-25/10; 51 solo el 23/10). Corte exacto: todos los correctos <= 129,9 s, todos los fallidos que terminaron >= 130,3 s. `--cpu-boost` ya estaba activo | **resuelto** el 25/10 (revision 00061, solo sonda 16 x 15 s). Arranques posteriores: 115,8 s y 126,0 s, aceptados en el 9.o intento (margen ~110 s) |
| H-16 | Un rebuild resolvia 14 paquetes en versiones distintas a produccion (3 con salto mayor) y anadia `tzdata`: las dependencias transitivas no estaban fijadas | **resuelto** con `constraints.txt` |
| H-17 | Los modelos se descargan en el build en su ultima revision publicada (sin fijar). Hoy coinciden con produccion (verificado por hash de revision); un cambio en HuggingFace desalinearia los vectores del indice FAISS con el texto codificado | pendiente: fijar la revision de cada modelo en el `Dockerfile` |
| H-18 | El repo no tiene `.gitattributes`: con `core.autocrlf=true`, en Windows los `.sh` salen con CRLF y no se pueden ejecutar con bash | pendiente (p. ej. `*.sh text eol=lf`) |
| H-19 | **`venv_fase0/Scripts/` esta bajo control de versiones** (lanzadores `.exe` del entorno virtual de Windows del servicio). Las instalaciones de pip del paso 1 (`numpy`, `idna`, `pip`, `pytest`, `pygments`) dejaron en `git status` 6 ficheros modificados (`f2py.exe`, `idna.exe`, `numpy-config.exe`, `pip.exe`, `pip3.exe`, `pip3.11.exe`) y 3 nuevos (`pytest.exe`, `py.test.exe`, `pygmentize.exe`). La regla `venv/` (linea 2 del `.gitignore` raiz) no cubre `venv_fase0`. `Lib/` no aparece en `git status`; [H] la excluye la regla `lib/` (linea 59, de la plantilla de Python) porque git en Windows ignora mayusculas (`core.ignorecase`); confirmar con `git check-ignore -v`. Riesgo: un `git add .` o "Stage All" meteria binarios del entorno en un commit. Misma raiz que H-14 (el entorno se colaba en la imagen) | pendiente: dejar de seguir la carpeta (`git rm -r --cached`, no borra nada del disco) y anadirla al `.gitignore` |

### 15.5 Abierto

- **Tendencia del arranque:** la fase de ColBERT paso de 72,6 s (18/10) a 84-135 s
  (21-25/10). Causa desconocida. Seguir el margen frente a la sonda de 240 s.
- H-13, H-17, H-18 y H-19.
- Pasos 3 y 4 de esta spec.

### 15.6 Lecciones

1. **Comparar artefactos, no suponer.** Codigo, paquetes y modelos de la imagen
   nueva se compararon con los de la imagen desplegada antes de subirla; asi
   aparecieron H-14, H-16 y la verificacion de H-17.
2. **Ante un fallo tras un despliegue, preguntar si ya pasaba antes.** Los
   logs de UNA revision sugerian "la imagen nueva arranca mas lento"; los del
   servicio completo mostraron que produccion llevaba dias fallando (H-15).
3. **Un cambio por despliegue.** La sonda se corrigio primero con la imagen
   antigua (00061) y el codigo nuevo despues (00062): cada resultado tiene una
   sola causa posible.
4. **Vigilar el margen, no solo el exito.** "Aceptada en el 9.o intento" en
   00061 y 00062 significa que con la sonda antigua habrian pasado por poco.
5. **Comandos sin huecos que rellenar.** Un `<DIGEST>` literal llego a Cloud
   Run. Dar comandos completos cuando el valor ya se conoce.
6. **Consultas que filtran sin que se vea.** El enlace del error de despliegue
   filtraba por revision; ampliar el rango de tiempo no cambiaba nada.

---

## 16. Cierre del paso 3 -- filtro en el monolito, flag apagado (29/10/2026)

### 16.1 Que se entrego

Un commit en `feature/visual_search`, subido como `937d43e` (`39b39af..937d43e`;
su contenido se confirma con `git show --stat 937d43e`: deben ser los 8
ficheros siguientes). Configuracion: `RECS_VISUAL_FILTER_IN_SEARCH: "0"` en
`env-vars.yaml` (comprobado en el servicio: `value: '0'`).

| Fichero | Cambio |
|---|---|
| `src/recommenders/f08_similarity_resolution.py` | `VisualFilter`, `build_visual_filter()`, flag `visual_filter_in_search_enabled()` (cabecera: orden de marcha atras) |
| `src/api/services/colbert_client.py` | `FilteredVisualResult`, `search_filtered()` |
| `src/api/core/mcp_conversation_handler.py` | F-08C y Fase A conectadas al filtro (+274 -81) |
| `tests/unit/test_f08_similarity_resolution.py` | 17 tests (filtro y flag) |
| `tests/unit/test_colbert_client_search_filtered.py` (nuevo) | 9 tests del cliente |
| `tests/characterization/equiv_harness_e5.py` (nuevo) | oraculo P1-P3 |
| `tests/characterization/equiv_harness_handler_e5.py` + `_blocks.py` (nuevos) | prueba diferencial del handler |

### 16.2 Diseno final (lo que cambio respecto a la seccion 6)

1. **Orden de logs intacto con el flag apagado.** `extract_categories_from_query`
   escribe en INFO; subir la resolucion sobre la busqueda SIEMPRE habria
   cambiado el orden y el numero de lineas. El calculo se encapsula en
   `_c08_prepare_pool_request()` / `_f08_prepare_pool_request()` (mismo
   codigo): con el flag activado se llama antes de buscar; con el
   desactivado, dentro del bloque, en el mismo punto que antes.
2. **`anchor_found` en tres decisiones**: la entrada al bloque de F-08C, y en
   Fase A el fallback por imagen y la entrada al bloque (F7 era doble en
   Fase A).
3. **Aviso de divergencia** tras el filtro posterior (que se conserva como
   defensa), en Fase A solo si el pool viene de la busqueda filtrada: el
   fallback por imagen no se filtra (4.2) y avisaria en falso.
4. **`build_visual_filter` tolerante a `product_type` None** (recorre el
   catalogo entero; un solo None no debe tumbar todas las peticiones).
5. **El cliente EXIGE los campos del contrato**: sin `anchor_found` la
   respuesta cuenta como fallo, no se supone un valor.

### 16.3 Evidencia

| Capa | Resultado |
|---|---|
| Oraculo P1-P3 | 20.000 casos, 0 fallos, 5/5 mutantes (laboratorio y Windows) |
| Prueba diferencial del handler | D1 (flag apagado: resultado, llamadas, relleno y logs identicos), D2 (flag activado == pool infinito), D3 (rama vacia, sin fallback por imagen), D4 (fallo del servicio): 400 escenarios, 0 fallos, 5/5 mutantes, en el laboratorio y en Windows. Cubre los 4 caminos y 12 escenarios por imagen |
| Oraculos previos | `pool_request` 40.000 casos + 8/8; 02/10 40.000 casos: 0 divergencias |
| Suite (`git worktree` como linea base, mismo `.env`) | 723 -> 749: +26 tests nuevos, todos en `passed`; 0 fallos nuevos, 0 cambios de estado |
| Produccion (00329 frente a 00330, guion de 9 turnos, linea base tomada el mismo dia) | 8 turnos comparables IDENTICOS caracter a caracter (48 lineas F-08 sin normalizar). Turno 4 con otra ancla (ver H-21): misma ruta y decision (`category_query`, `happy`, 8 AROS); 123 -> 124 candidatos. 0 lineas `E5`. 0 ERROR. Ningun tipo de aviso nuevo: los del camino de cada peticion, identicos (10 + 4 + 4); la caida 222 -> 130 avisos es entera de la sincronizacion de fondo con Shopify (`batch throttled`) |
| Imagen desplegada | digest `sha256:f6ea43c8...cd1d` == el del `docker push` |

### 16.4 Hallazgos

| Id | Hallazgo | Estado |
|---|---|---|
| H-20 | **`venv_fase0` tambien esta en la imagen de produccion del MONOLITO**: 2,2 GB de 3,0 GB en `/app` (comprobado con `du`). El `.dockerignore` de la raiz excluye `venv/` y `.venv/`, patrones que solo afectan a la raiz del contexto, no a `src/api/services/embedding-service/venv_fase0`; ningun patron usa `**/` (tampoco `__pycache__/`). Efectos medidos en el build del 29/10: contexto de 2,47 GB, `COPY src/` 264 s, `chown -R` 404 s. Misma raiz que H-14 y H-19 | pendiente: `**/venv_fase0/` (o lista blanca) en el `.dockerignore` raiz; resolver junto con H-19. **Actualizacion: corregido en el repo el 30/10 y VALIDADO EN PRODUCCION (revision 00333-h5z; ver 17.4)** |
| H-21 | **El guion de 9 turnos no es del todo reproducible**: el turno 3 (`Muestrame aros`) elige los productos con `random.sample` (`smart_sample_across_categories`, `improved_fallback_exclude_seen.py` ~1221), asi que el ancla pulsada en el turno 4 cambia entre ejecuciones (29/10: `aros-fiesta-mia-...` frente a `aros-isadora-flor-metal-plateado`) | para el paso 4: fijar el ancla del turno 4 abriendo directamente la pagina de un aro concreto |
| H-22 | La prueba diferencial imprime en consola el DEBUG/INFO de `improved_fallback_exclude_seen` en el entorno Windows (algun modulo configura un manejador en el logger raiz). No afecta a la comparacion (lee de su propio manejador) | menor: silenciar la propagacion durante la ejecucion |
| H-6 (actualizado) | OpenRouter responde que `liquid/lfm-...` **ya no esta disponible** (`no longer available`): no es un 404 transitorio sino la retirada del modelo. En el guion del 29/10, 10 de 10 turnos cayeron a GPT-4o-mini | pendiente: decidir el modelo principal |

### 16.5 Lecciones

1. **`>` en Windows PowerShell corrompe la salida de programas externos**
   (UTF-16, caracteres no ASCII rotos, salto final anadido). Para guardar
   bytes exactos: `cmd /c "programa > fichero"`. El extractor de la prueba
   diferencial detecta el caso y lo explica.
2. **Copias de laboratorio desfasadas.** La copia del test de f08 del
   laboratorio era ANTERIOR al paso 2b: escribirla habria borrado el fixture
   que cierra la fuga del `.env`. La comprobacion previa de la base lo evito;
   los cambios se reconstruyeron sobre la version real.
3. **Una defensa necesita su propia senal.** El filtro posterior oculta en el
   resultado un filtro mal construido; solo el aviso de divergencia lo revela,
   y la prueba diferencial lo vigila.
4. **Linea base en el mismo momento.** En produccion se compararon dos
   revisiones con el guion ejecutado el mismo dia, para no confundir el
   cambio con derivas ajenas (catalogo, embedding service, Shopify).
5. **`git worktree` para la linea base de la suite**, en vez de `git stash`
   (incidente del paso 2): una segunda copia de trabajo de `HEAD`, sin tocar
   la propia.
6. **"La herramienta dijo que funciono" no es "funciono".** Una escritura sin
   respuesta en 4 minutos no creo el fichero; se detecto porque cada
   escritura se verifica por hash.

---

## 17. Cierre del paso 4 -- filtro activado en produccion (29/10/2026)

### 17.1 Activacion

| Revision | Imagen | Flag | Resultado |
|---|---|---|---|
| 00330-vwb | `sha256:f6ea43c8...` | `0` | linea base (seccion 16) |
| 00331-m89 | la misma | `1` | **fallo de la sonda de arranque** (H-23); no llego a servir |
| **00332-d87** | **la misma** | **`1`** | sirve el 100 % desde el 29/10 ~16:10 UTC |

La 00332 se desplego desde la consola de Cloud Run: el unico cambio respecto a
la 00330 es la variable. `env-vars.yaml` se actualizo a `"1"` en el repo
(30/10) para que un despliegue por linea de comandos no apague el filtro en
silencio.

### 17.2 Evidencia (guion de 9 turnos, 00330 frente a 00332, mismo dia)

Ancla del turno 4 FIJADA (`aros-isadora-flor-metal-plateado`, H-21): los 9
turnos son comparables.

| Comprobacion | Resultado |
|---|---|
| Filtro aplicado | 1 linea `E5 filtro en busqueda` por turno F-08 (9/9); `devueltos = min(top_k, eligible)` en todos; `exclude=1` en el primer turno (solo el ancla) |
| **P3 en produccion** | los productos de la categoria pedida (`en_pool`) NO bajan en ningun turno; suben en 5 (62->63, 50->56, 124->125, 17->30, ...) |
| Pool util | palazzo: de 7-14 candidatos a 57-68; vestido corto: 31 -> 100; bolsos: 78/71 -> 100/109 |
| **Mejora visible** | T5 y T7 (palazzo-silvia-negro): de 7 a **8** productos (`alternatives` 2 -> 3); aparece LEGGINGS como alternativa en T5 |
| Contratos sin cambio | T1, T2, T4, T8, T9, T10 (el pool ya bastaba); **B.2 (T6)** identico: `principal=0[] alternatives=8['FALDAS'] exhausted=True` |
| Limite real | PANTALONES sigue en 5 en T5/T7: el catalogo no tiene mas; el filtro no inventa productos |
| Defensa | **0** avisos `E5 divergencia` |
| Avisos / errores | ningun tipo nuevo; los del camino de cada peticion, identicos (10 + 4 + 4); 0 ERROR en la 00332 |
| Latencia | `/search-filtered` en el servicio: 0,7-3,4 ms (mediana 1,9 ms), 9 llamadas |

Nota sobre T7: faltaba la linea `F-08C pool insuficiente`. NO se perdio en el
hueco entre ficheros descargados (todo el turno ocurrio a las
16:23:11,499-11,557, antes del hueco de 16:23:14): el codigo solo la escribe
con menos de 8 candidatos (`len(_c08_candidates) < n_recommendations`), y con
el filtro habia 57. Su ausencia ES la mejora.

### 17.3 Hallazgo

| Id | Hallazgo | Estado |
|---|---|---|
| H-23 | **Margen insuficiente en la sonda de arranque del MONOLITO** (misma clase que H-15): `initialDelaySeconds=10`, `periodSeconds=10`, `failureThreshold=20` (~210 s). Arranques medidos de la MISMA imagen: 97,8 s (00329), 104,9 s (00330), 146,7 s (00332) y >201 s (00331, rechazada a los 201 s). El flag no influye: se lee al procesar cada peticion, nunca al arrancar | pendiente: ampliar a `failureThreshold=24` x `periodSeconds=10` = 240 s (maximo de Cloud Run) en el comando de despliegue; [H] H-20 podria acortar el arranque (sin medir). **Actualizacion 30/10: sonda ampliada a 240 s en la revision 00333-h5z; arranque medido 108,0 s (menos de la mitad del margen). La hipotesis de que H-20 acorte el arranque queda SIN CONFIRMAR: una sola muestra, dentro del rango ya observado (98-147 s)** |

### 17.4 Correccion de H-20 (30/10/2026)

Bloque nuevo al final del `.dockerignore` raiz (las 16 lineas existentes
intactas): `**/venv_fase0/`, `**/node_modules/`, `venv.test/`,
`**/__pycache__/`, `**/*.py[cod]`, `**/.pytest_cache/`.

Alcance justificado: en el repo hay cuatro entornos virtuales (`pyvenv.cfg`):
`venv/` y `.venv/` ya estaban excluidos; `venv.test/` engordaba el contexto;
`venv_fase0` llegaba a la imagen. Hay dos `node_modules` dentro de `src/`
(`src/frontend/`, `src/api/mcp/nodejs_bridge/`) que `COPY src/` tambien
copiaba; la imagen no tiene Node.js y el widget se sirve desde `static/`.

Validacion en el laboratorio (logica de exclusion de la libreria oficial de
Docker sobre una replica de las rutas reales): 10/10 ficheros necesarios
entran (codigo, `data/`, `static/widget/`, `models/`, `requirements`); 12/12
artefactos quedan fuera; con el `.dockerignore` original la simulacion
reproduce H-20.

**Validacion en el build real (30/10)** -- inventario de `/app` de la imagen
anterior (`sha256:f6ea43c8...`) frente a la nueva: 0 ficheros nuevos; 60.097
quitados, TODOS dentro de los artefactos; codigo `.py`: 0 nuevos o
modificados y 0 quitados fuera de los artefactos (los 14.455 `.py` quitados
son de `venv_fase0`/`node_modules`). `/app`: **3,0 GB -> 559 MB** (-81 %).
Build: 1.830 s -> 122 s (`chown -R`: 404 s -> 11 s).

**Validacion en produccion (30/10)** -- revision `retail-recommender-00333-h5z`,
imagen `sha256:c02f4a43...` desplegada por digest, flag `1`, sonda de 240 s
(H-23). Guion de 9 turnos frente a la 00332 (mismo codigo y mismo flag, ocho
horas despues): **9/9 turnos IDENTICOS caracter a caracter** (62 lineas F-08,
incluidas las 9 `E5`). Ningun error de importacion, fichero no encontrado ni
traceback; 0 avisos `E5 divergencia`; avisos del camino de cada peticion
identicos (10 + 4 + 4). Los tres tipos de aviso que no estaban en la 00332
(`Throttled` en precios y 3 productos con `CLP_RATES` de respaldo) son los
mismos que la 00329 (imagen antigua) tuvo el 29/10 por la manana: limitacion
de Shopify, ajena a la imagen.

### 17.5 Seguimiento con trafico real (pendiente)

El guion demuestra el mecanismo; el efecto sobre la experiencia se mide con
trafico real, misma ventana antes/despues del 29/10 ~16:10 UTC, en Cloud
Logging: proporcion de turnos con `principal` completo; frecuencia de
`exhausted=True`; numero medio de productos devueltos (7 frente a 8 en el
guion); frecuencia de `pool insuficiente`; avisos `E5 divergencia` (deben
seguir en 0); sesiones reales con las anclas del 05/10 y 07/10.

### 17.6 Lecciones

1. **Una ausencia en un log se interpreta conociendo cuando se escribe la
   linea.** "Falta `pool insuficiente`" admitia dos lecturas opuestas (dato
   perdido / problema resuelto); la decidieron las marcas de tiempo y la
   condicion del codigo.
2. **Fijar las entradas no deterministas del guion** (H-21): con el ancla del
   turno 4 fija, los 9 turnos pasaron a ser comparables.
3. **Desplegar desde la consola desincroniza la configuracion del repo.** El
   flag activado en Cloud Run no estaba en `env-vars.yaml`; el siguiente
   despliegue por linea de comandos lo habria apagado sin aviso.
4. **El mismo arranque varia el doble entre ejecuciones** (98 s a >201 s): un
   margen que cubre el caso medio no cubre la cola (H-15, H-23).
