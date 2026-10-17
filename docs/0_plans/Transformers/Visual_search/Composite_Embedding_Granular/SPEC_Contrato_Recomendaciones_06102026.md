# SPEC — Contrato de Recomendaciones: `principal` / `alternatives`

**Fecha:** 06/10/2026
**Estado:** Especificación aprobada para implementar — sin código escrito todavía
**Autor del encargo:** Yasmani (decisión estratégica del 06/10/2026)
**Contexto previo:** `Evaluacion_Integral_16092026/DCT_Cierre_Sesion_01102026.md`, Addendum A.11 (backlog consolidado de gaps)
**Relacionado:** `BACKLOG_Busqueda_por_Atributos_Color_24072026.md` (mismo arbol de directorios) — ver seccion 11

---

## 1. Proposito

Hoy el handler devuelve una **lista plana de 8 productos** que mezcla tres fuentes con significados incompatibles (pool visual, catalogo por categoria, preferencias historicas) bajo una unica etiqueta "RECOMENDADO PARA TI". Esa estructura es la causa raiz comun de los cinco gaps estructurales E1–E5 del Addendum A.11.

Esta especificacion define un contrato de datos que **separa lo pedido de la alternativa**, conserva la procedencia de cada item hasta el frontend, y hace imposible por construccion que un item de categoria ajena supere en ranking a uno de la categoria pedida.

### 1.1 Principio rector

> Cada producto lleva su procedencia, y el orden nunca cruza bloques.

### 1.2 Decision estrategica que lo justifica (A.11.5)

Se prioriza el contrato de datos sobre la mejora de la recuperacion. La estructura es el invariante; la calidad del pool es lo que se ajusta de forma continua. Mejorar primero la recuperacion reduce la *frecuencia* de una experiencia deshonesta sin eliminarla — eso es un parche. Fijar primero la estructura hace que el peor caso ya sea honesto, y que cada mejora posterior del pool solo agrande el bloque principal.

---

## 2. Hallazgos que fundamentan el diseno

Verificados contra el codigo real el 06/10/2026, no asumidos.

### 2.1 No existe ninguna puntuacion real de parecido

`colbert_client.py` — los tres metodos de busqueda (`search_by_product_id`, `search_by_product_id_with_text_boost`, `search_by_image`) estan anotados `-> Optional[List[str]]` y devuelven `data['product_ids']`. La respuesta del servicio trae `product_ids` y `latency_ms`; **no se lee ninguna puntuacion**.

Consecuencia: el `similarity_score` que produce `normalize_recommendation_dict` es **fabricado** (`score_start - rank * score_step`). El "% match" que muestra el widget no es una medida degradada: es la posicion de llenado.

Evidencia de pantalla (sesion 05/10/2026, ancla "Clutch Indio Uma"):

| Posicion | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Widget | 100% | 98% | 96% | 94% | 92% | 87% | 85% | 83% |
| Codigo | 1.0 | −0.02 | −0.02 | −0.02 | −0.02 | **salto 0.05** | −0.02 | −0.02 |

El salto de 92 a 87 no significa "menos parecido": marca el inicio del relleno desde catalogo.

**RESUELTO el 06/10/2026** — ver seccion 2.3: las puntuaciones existen, se calculan en cada busqueda y se descartan en origen.

### 2.2 Ocho puntos de retorno y un reordenamiento global

Dentro de `get_mcp_conversation_recommendations()` (`mcp_conversation_handler.py`, lineas 98–3158) hay **ocho `return` de recomendaciones**:

| Linea | Retorna | Ruta |
|---|---|---|
| 1443 | `_b08_recs` | F-08B — completar outfit |
| 1932 | `_c08_recs` | F-08C — camino feliz (Turn 2+) |
| 2022 | `_c08_recs` | F-08C — parcial + relleno |
| 2190 | `recommendations` | smart_fallback (Turn 2+) |
| 2462 | `_f08_recs` | F-08 Fase A — camino feliz (Turn 1) |
| 2559 | `_f08_recs` | F-08 Fase A — parcial + relleno |
| 2587 | `_f08_recs` | F-08 Fase A — relleno fallido, solo visual |
| 2765 | `recommendations` | ruta estandar (TF-IDF) |

Ademas, en la ruta estandar (lineas 2699–2763) el **bonus de coleccion** (`COLLECTION_BOOST = 0.15`) modifica `similarity_score` y **reordena la lista entera**:

```python
recommendations = sorted(recommendations,
    key=lambda r: r.get("similarity_score", r.get("score", 0)), reverse=True)
```

Hoy no afecta a las rutas visuales porque estas salen antes (early-return). **Pero en cuanto exista el contrato, ese `sorted` global romperia los bloques**: podria subir una alternativa por encima de lo principal. Es una bomba de relojeria, no un gap separado.

**Implicacion de diseno:** construir el contrato en los ocho puntos recrearia exactamente la duplicacion que el paso 1 acaba de eliminar. El contrato **debe nacer en un unico constructor compartido**.

### 2.3 Las puntuaciones de parecido existen y se descartan en origen

Verificado en `src/api/services/embedding-service/visual_retriever.py`. Los **cinco** metodos de busqueda usan el mismo patron:

```python
_, indices = self._faiss_index.search(vec, top_k + 1)   # lineas 852, 892, 982, 1080, 1228
```

`faiss.search()` devuelve `(distancias, indices)`. **El guion bajo descarta las distancias.** Como el indice es `IndexFlatIP` con vectores normalizados — el propio codigo lo documenta en las lineas 1216-1220 — esas distancias **son la similitud coseno**: exactamente la medida de parecido real que el sistema lleva fingiendo desde el principio.

La puntuacion se calcula en cada busqueda y se tira a un caracter de donde nace. Nunca ha salido del servicio.

**Consecuencias para esta spec:**

1. `visual_score` deja de ser un campo nullable a la espera de infraestructura futura: pasa a ser **el campo principal** de parecido.
2. El "% match" del widget **no hay que retirarlo: hay que hacerlo verdadero** (ver 10.1).
3. El cambio es pequeno y en tres sitios: el servicio anade `scores` al JSON de respuesta, `colbert_client` los lee en vez de devolver solo `product_ids`, y el constructor del contrato los coloca en el item.
4. `visual_rank` se mantiene como respaldo mientras el cambio se propaga, y para items cuyo origen no es el pool visual.

### 2.4 El filtro de categoria dentro de la busqueda YA EXISTE (ruta outfit)

Hallazgo no buscado, encontrado al verificar 2.3. `search_outfit_by_image()` (lineas 1228-1247) ya hace exactamente lo que falta en las rutas de similitud:

```python
_, indices = self._faiss_index.search(composite, search_pool)   # pool AMPLIO
...
if has_category_map:
    for idx in indices[0]:
        if self._category_map[idx] == category:                 # filtro DENTRO
            category_ids.append(self._id_map[idx])
```

Y el comentario de las lineas 1226-1227 dice literalmente: *"search_pool > top_k_per_category para que haya candidatos suficientes DESPUES del filtro de categoria"*. El problema E5 ya fue resuelto, para otra ruta.

**`_category_map` es infraestructura probada en produccion** (sprint S1): paralelo a `_id_map`, se construye en la indexacion (linea 658), se persiste a disco (410-414), se extiende en indexaciones incrementales (821-822), y degrada con elegancia a `degraded_no_category_map` si falta.

**Consecuencia:** el arreglo de E5 **no requiere construir infraestructura nueva**, solo extender a las rutas de similitud lo que outfit ya usa. Ver seccion 12.1.

---

## 3. El contrato

Modulo nuevo: `src/recommenders/recommendation_set.py`. Sin dependencias del proyecto; todo lo externo llega inyectado. Mismo criterio que `f08_similarity_resolution.py`.

```python
@dataclass(frozen=True)
class RequestSpec:
    """Que cuenta como 'lo pedido' bajo esta intencion."""
    categories: Set[str]              # tipos de producto que cuentan como principal
    attributes: Dict[str, str]        # restricciones duras adicionales; VACIO hoy
                                      # p.ej. {"color": "verde"} -- ver seccion 11

@dataclass(frozen=True)
class Block:
    items: List[Dict]
    categories: List[str]             # tipos que contiene de hecho, en orden de aparicion
    exhausted: bool                   # solo significativo en principal -- ver 3.2

@dataclass(frozen=True)
class Meta:
    anchor_id: Optional[str]
    anchor_type: Optional[str]
    request: RequestSpec
    n_requested: int
    route: str                        # f08a | f08c | f08b | smart_fallback | standard

@dataclass(frozen=True)
class RecommendationSet:
    intent: str                       # similarity | outfit_complement | category_query | generic
    principal: Block
    alternatives: Block
    meta: Meta
```

### 3.1 Esquema por item

Se conserva el esquema canonico actual de `normalize_recommendation_dict` (`id`, `title`, `similarity_score`, `score`, `handle`, `image_url`, `product_data`, `source`) y se anaden **dos campos**:

```python
"origin": "visual" | "catalog" | "behavioral",
"visual_rank": int | None,   # posicion 0-indexed en el pool FAISS; None si no vino de ahi
```

- `origin` va **por item, no por bloque**: `principal` puede mezclar procedencias de forma legitima (bolsos del pool visual + bolsos del catalogo). Todos son bolsos, pero solo los primeros tienen vecindad visual medida.
- `visual_score` es la similitud coseno real devuelta por FAISS. Disponible en cuanto se propague el cambio de 2.3; `None` para items que no vienen del pool visual.
- `visual_rank` es el respaldo ordinal mientras ese cambio se propaga, y queda como dato util en si mismo (posicion en el vecindario).
- `score` se mantiene **solo por compatibilidad** con los consumidores actuales. Deja de ser lo que el widget muestre como parecido.

### 3.2 Semantica de `exhausted`

`principal.exhausted = True` **solo** si se consulto al catalogo por esa categoria y no habia mas productos disponibles tras las exclusiones.

`False` si `principal` quedo corto por agotamiento del **pool visual** aunque el catalogo tenga mas.

Esta distincion es exactamente la que faltaba el 04/10/2026 (senal sobrecargada, A.10). Aqui es un booleano con un unico significado, no un campo reinterpretable. Es ademas la condicion que gobierna el boton de reinicio en UI (seccion 10.2).

---

## 4. Reglas de particion: una funcion, cuatro intenciones

El contrato **no sabe** que es "lo pedido". Se lo dice la intencion, via `RequestSpec`:

| Intencion | `principal` contiene | `alternatives` contiene | `RequestSpec.categories` |
|---|---|---|---|
| `similarity` | el tipo exacto del ancla | tipos hermanos de la familia | `{anchor_type}` |
| `outfit_complement` | los tipos que completan el conjunto | cualquier cosa fuera de esos | slots objetivo del outfit |
| `category_query` | las categorias detectadas en el texto | relleno de otras | categorias extraidas de la query |
| `generic` | todo | vacio | conjunto vacio = todo es principal |

Cada ruta sabe cual es su conjunto, y es la unica que puede saberlo. Las cuatro usan **la misma funcion de particion**, sin casos especiales.

### 4.1 Nota sobre `outfit_complement`

Bajo esta intencion, mezclar categorias **es lo correcto**, no un defecto. Un collar que completa un vestido va en `principal`, porque bajo esa intencion el collar **es** lo pedido. El contrato lo expresa sin excepciones: lo que cambia no es la logica, solo el contenido de `RequestSpec.categories`.

Esta es la razon por la que `principal` se define por la **intencion** y no por la categoria (decision de Yasmani, 06/10/2026).

### 4.2 Predicado de pertenencia

```python
def belongs_to_principal(item, request: RequestSpec, type_of) -> bool:
    if request.categories and type_of(item).upper() not in {c.upper() for c in request.categories}:
        return False
    for attr, expected in request.attributes.items():     # vacio hoy
        if str(item.get("product_data", {}).get(attr, "")).lower() != expected.lower():
            return False
    return True
```

Con `attributes` vacio el comportamiento es identico al de una particion solo por categoria.

---

## 5. Regla de tope de alternativas

Decision de Yasmani (06/10/2026):

```
max_alternativas = min(n_pedidos - len(principal), 4)
```

Con `n_pedidos = 8`:

| `len(principal)` | alternativas | total devuelto |
|---|---|---|
| 6 | 2 | 8 |
| 4 | 4 | 8 |
| 2 | **4** (no 6) | **6** |
| 0 | **4** (no 8) | **4** |

**Consecuencia asumida deliberadamente:** a veces se devolveran menos de 8 productos. Seis resultados honestos valen mas que ocho con seis de relleno.

`principal` **puede quedarse vacio** (decision de Yasmani). El widget decide si dibuja el bloque.

### 5.1 El tope es configurable — desplegamos en 8, bajamos a 4 tras validar

Decision de Yasmani (06/10/2026). El tope se lee de la variable de entorno **`RECS_MAX_ALTERNATIVES`**; el modulo expone `MAX_ALTERNATIVES_TARGET = 4` para que el objetivo de producto no se pierda aunque el valor en vigor sea otro.

| | Valor | Efecto |
|---|---|---|
| **Despliegue inicial** | `8` | El tope **nunca muerde**: `min(8 - len(principal), 8) == 8 - len(principal)`. El numero TOTAL de productos es **identico al de hoy** |
| **Objetivo tras validar** | `4` | Entra en vigor la tabla de arriba; empieza a devolverse menos de 8 cuando no hay material |

**Por que:** la fase 1 ya cambia el **orden** (elimina E2). Si ademas cambiara **cuantos** productos se devuelven, dos efectos observables se mezclarian en el mismo despliegue y seria imposible atribuir una regresion a uno u otro. Con el tope en 8 se despliega **un solo cambio observable a la vez**.

**Como bajarlo:** `RECS_MAX_ALTERNATIVES=4` en Cloud Run. `build()` resuelve el tope **en cada llamada**, no en el default de la firma, asi que el cambio aplica **sin redeploy de imagen**. `0` es valido y desactiva las alternativas por completo — palanca de emergencia. Un valor ausente, no numerico o negativo degrada al de despliegue con un `logger.warning`: un tope mal configurado nunca debe tumbar las recomendaciones.

---

## 6. Orden, y el bonus de coleccion

### 6.1 El aplanado nunca cruza bloques

```python
def to_flat_list(self) -> List[Dict]:
    return self.principal.items + self.alternatives.items
```

Esta linea elimina **por construccion** el gap E2 (un cinturon por encima de un bolso). No es una regla de ordenacion que alguien pueda saltarse: son listas distintas.

### 6.2 El bonus de coleccion se aplica DENTRO de cada bloque

Decision de Yasmani (06/10/2026): se incluye en este trabajo, no se deja como gap aparte.

El reordenamiento de las lineas 2751–2757 pasa a aplicarse **por bloque**:

```python
principal.items   = reorder_by_collection(principal.items, current_collections)
alternatives.items = reorder_by_collection(alternatives.items, current_collections)
```

Un producto de la misma coleccion sube **dentro de su bloque**, nunca lo atraviesa. Sin este cambio, el `sorted` global vaciaria de sentido todo el contrato en la ruta estandar.

---

## 7. Hechos para el redactor (LLM)

```python
def to_prompt_facts(self) -> Dict:
    return {
        "intent": self.intent,
        "principal_count": len(self.principal.items),
        "principal_categories": self.principal.categories,
        "alternatives_count": len(self.alternatives.items),
        "alternatives_categories": self.alternatives.categories,
        "catalog_exhausted": self.principal.exhausted,
    }
```

**Hechos, no instrucciones.** Esta es la pieza que ataca el fallo confirmado el 05/10/2026: el fix del 04/10 logro que el LLM dejara de **afirmar en falso** el agotamiento, pero **no** logro que **revelara** la mezcla — en el unico turno donde la senal se emitio, el LLM tampoco la menciono pese a pedirselo el prompt (A.11.1, nota sobre E4).

Mencionar lo que uno tiene delante es natural; cumplir una instruccion entre muchas es opcional. Por eso la revelacion se resuelve con **estructura**, no con prompt.

Al adoptar `to_prompt_facts()`, se jubila el parche del 04/10 (`_exhausted_kind` + rama `result_mixed` en `mcp_personalization_engine.py`): con hechos bien estructurados ya no hace falta prohibirle mentir.

---

## 8. Donde nace el contrato

Un unico constructor compartido, invocado por cada ruta justo antes de su `return`:

```python
rset = RecommendationSet.build(
    intent="similarity",
    items=_c08_recs,                 # ya normalizados
    request=RequestSpec({anchor_type}, {}),
    n_requested=n_recommendations,
    anchor_id=_c08_pid, anchor_type=_c08_ctx_type,
    route="f08c", type_of=_c08_type_of,
    exhausted=<bool del relleno>,
)
mcp_context.recommendation_set = rset
return rset.to_flat_list()
```

Cada ruta aporta **solo lo que unicamente ella sabe**: su intencion, su `RequestSpec` y si el catalogo se agoto. Toda la logica de particion, tope, orden y hechos vive en el modulo.

---

## 9. Migracion

| Fase | Alcance | Efecto visible |
|---|---|---|
| **1** | Modulo + los 8 call sites construyen el `RecommendationSet` y devuelven `to_flat_list()` | **Ninguno en la firma.** Desaparece el ranking invertido (E2) y el bonus deja de cruzar bloques |
| **2** | `mcp_personalization_engine` consume `to_prompt_facts()`; se retira el parche del 04/10 | El LLM revela la mezcla de forma natural (E4) |
| **3** | La API expone los bloques junto a la lista plana | El widget puede migrar a su ritmo |
| **4** | Se retira la lista plana y el "% match" | Cierre de E1 y E3 |

Las fases 1 y 2 son **backend puro** y entregan la mitad del valor sin tocar el frontend. La fase 3 es la de ciclo mas largo (frontend), por eso el contrato se define desde el dia uno aunque el widget tarde.

### 9.1 Compatibilidad

`to_flat_list()` devuelve exactamente el mismo tipo (`List[Dict]`) con el mismo esquema por item mas dos campos nuevos. Ningun consumidor actual se rompe: los campos extra se ignoran.

---

## 10. UX / UI (fase 3)

### 10.1 Separacion visual de bloques

El contrato no sirve de nada si el widget pinta los dos bloques igual. Por orden de impacto frente a esfuerzo:

1. **Encabezado por bloque.** Hoy hay un unico "RECOMENDADO PARA TI". Pasa a dos, con el texto segun la intencion:
   - `similarity`: **"Similares a este"** / **"Tambien podria combinar"**
   - `outfit_complement`: **"Para completar el look"** (sin bloque de alternativas)
   - `category_query`: **"<Categoria> que tenemos"** / **"Tambien podria interesarte"**
2. **Hacer verdadero el "% match"** (revisado el 06/10 tras 2.3). La recomendacion inicial era retirarlo por ser un numero inventado. Ahora que sabemos que la similitud coseno real se calcula y se descarta, la opcion correcta es **propagarla** y mostrarla solo donde existe:
   - items con `origin == "visual"`: mostrar `visual_score` real.
   - items con `origin == "catalog"` o `"behavioral"`: **no mostrar porcentaje** — no hay parecido medido, y fingirlo es el defecto original.
   - Mientras el cambio no este desplegado, retirar el porcentaje es preferible a seguir mostrando la posicion de llenado.
3. **Tratamiento visual mas ligero** para alternativas: tarjeta algo menor o etiqueta discreta con el tipo ("Cinturon").

**Regla rectora:** el usuario nunca deberia tener que deducir en que bloque esta una tarjeta.

### 10.2 Reinicio de catalogo cuando `principal` esta vacio

Propuesta de Yasmani (06/10/2026). Convierte un callejon sin salida en dos caminos:

> *"Ya te he mostrado todos los bolsos que tengo. Quieres que empiece de nuevo?"*
> **[Ver bolsos otra vez]**
> **Tambien podria combinar:** …alternativas…

**Condicion de aparicion:** solo cuando `principal.exhausted == True`, es decir cuando se pregunto al catalogo y no habia mas — no cuando el pool visual se quedo corto. Es precisamente la distincion que introduce 3.2.

**Detalle de implementacion a resolver:** el reinicio debe ser **solo de esa categoria**, no de todo `shown_products`. Si el usuario lleva 40 productos vistos entre bolsos, vestidos y joyas y pide reiniciar bolsos, borrar los 40 le haria repetir vestidos que ya descarto. Hoy `shown_products` es un `set` plano sin categoria; hara falta poder filtrarlo por tipo. Se incluye en el alcance de este trabajo.

---

## 11. Relacion con la busqueda por atributos (color)

Ver `BACKLOG_Busqueda_por_Atributos_Color_24072026.md`.

Hay que distinguir dos mecanismos que ese backlog ya separa bien:

- El **empujon suave** via `alpha` en el composite embedding (seccion 3.2 del backlog): el modelo "cree" que algo se ve verdoso, sin garantia.
- La **red de seguridad** (seccion 3.3 del backlog): verificar el resultado contra el dato real del catalogo antes de mostrarlo. **Este es el mismo mecanismo que el filtro duro de categoria.**

Y "vestidos similares pero verdes" se expresa en este contrato sin ninguna pieza nueva:

| Bloque | Contenido |
|---|---|
| `principal` | vestidos similares que **son verdes de verdad** (validado contra catalogo) |
| `alternatives` | vestidos similares de otros colores |

Por eso `RequestSpec` lleva `attributes: Dict[str, str]` desde el dia uno aunque hoy este siempre vacio. Cuando llegue el color, **solo hay que rellenarlo**: ni una rama nueva ni un caso especial.

**Conclusion:** si el contrato no se hace primero, la busqueda por color heredaria todos los defectos que este trabajo corrige — ocho vestidos mezclados, sin saber cuales son verdes, con un porcentaje inventado al lado.

---

## 12. Que cierra y que no

**Cierra** (gaps A.11.1): E1 lista plana, E2 ranking invertido, E3 porcentaje falso, E4 mezcla silenciosa. Y deja preparado el sitio para E5.

**NO cierra, y conviene decirlo:** el pool visual seguira quedandose corto en sesiones largas (E5). El contrato hace que el resultado sea **honesto**, no que sea **mejor**. Con el contrato, el sintoma cambia de forma pero no desaparece: el bloque principal se ira encogiendo turno a turno hasta quedar vacio. Sera honesto, pero seguira siendo una respuesta pobre sobre un catalogo que si tiene material.

### 12.1 E5 — plan de resolucion (3 niveles, habilitado por 2.4)

**Problema:** la busqueda tiene un presupuesto fijo de 50 vecinos que se gasta ANTES de aplicar el filtro de categoria y de descartar lo visto. Con 80 productos mostrados, casi todo el presupuesto se consume en productos ya descartados. Evidencia: sesion 05/10, pool con 0 CARTERAS mientras el catalogo si tenia (ningun `preferred exhausted` en 1.532 lineas de log).

**Gravedad:** el usuario deja de ver productos que existen; y la conversacion se degrada justo con el usuario mas comprometido — incentivo invertido: cuanto mas explora, peor le va.

| Nivel | Cambio | Coste | Efecto |
|---|---|---|---|
| **1** | `top_k = base + len(shown_products)` | Una linea | No resuelve la raiz, pero elimina el sintoma en sesiones normales. Desplegable ya, en paralelo al contrato |
| **2** | Filtro de categoria dentro de la busqueda: replicar en `search_by_product_id_with_text_boost` lo que `search_outfit_by_image` ya hace con `_category_map` (ver 2.4) | Medio | Se pasa de "los 50 mas parecidos, a ver cuantos son bolsos" a "los 50 bolsos mas parecidos". El pool deja de agotarse por contaminacion |
| **3** | El servicio acepta la lista de exclusiones y las aplica dentro de la busqueda | Medio | El presupuesto se gasta integro en candidatos utiles. Cierra el problema |

**Secuencia recomendada:** contrato primero — el nivel 2 cambia lo que devuelve el servicio y conviene tener ya el sitio donde encaja; ademas, el nivel 2 sin contrato volveria a producir una lista plana, mejor pero igual de opaca. El **nivel 1 se puede meter ya**, en paralelo.

**Sinergia a aprovechar:** las puntuaciones reales (2.3) y el filtro de categoria (nivel 2) tocan **los mismos metodos** del servicio. Si se van a abrir, conviene hacerlo una sola vez.

**Fuera de alcance** (siguen abiertos en A.11.2/A.11.3): B1 anclas en `shown_products`, B2 evasion de `strict_category` en cero, B3 intercalado en F-08C, B4 aviso en Fase A, B5 etiqueta equivocada, B6 desempate de familias, B7 texto en Fase A, C1 steering de `outerwear`, C2 LFM caido.

---

## 13. Riesgos

| Riesgo | Mitigacion |
|---|---|
| Ocho call sites tocados = ocho oportunidades de romper algo | Prueba diferencial por ruta, como en el paso 1. Fase 1 no cambia la firma |
| Devolver menos de 8 puede percibirse como regresion | Decision explicita de producto (seccion 5). Vigilar la tasa de abandono tras turnos con `principal` corto |
| El `sorted` global del bonus de coleccion | Se incluye en fase 1 (seccion 6.2), no se deja para despues |
| El widget tarda y el contrato queda sin consumir | Fases 1 y 2 ya entregan valor sin frontend |

---

## 14. Plan de validacion

Mismo estandar que el paso 1:

1. **Tests unitarios** del modulo: particion por intencion, tope, `exhausted`, aplanado, `to_prompt_facts`, bonus por bloque.
2. **Prueba diferencial por ruta**: bloque anterior vs bloque cableado, comparando retorno, logs y llamadas. Se espera **una unica diferencia intencionada**: el orden cuando habia inversion.
3. **Mutation testing** de la prueba diferencial.
4. **`ast.parse`** y comparacion byte a byte sandbox/repo.
5. **Validacion en produccion** con logs reales, ruta por ruta.

---

## 15. Estado de las decisiones

| Decision | Estado |
|---|---|
| `principal` puede quedarse vacio | **Aprobada** (Yasmani, 06/10) |
| Tope fijo de 4 alternativas | **Aprobada** (Yasmani, 06/10). **Configurable** via `RECS_MAX_ALTERNATIVES`; se despliega en **8** y se baja a 4 tras validar (ver 5.1) |
| `principal` definido por intencion, no por categoria | **Aprobada** (Yasmani, 06/10) |
| Bonus de coleccion dentro de cada bloque | **Aprobada** (Yasmani, 06/10) |
| `RequestSpec.attributes` desde el dia uno | Propuesta en esta spec — pendiente de confirmacion |
| "% match": hacerlo verdadero en vez de retirarlo | **Revisada 06/10** tras 2.3 — pendiente de confirmacion de Yasmani |
| Reinicio de catalogo por categoria | **Aprobada** como idea (Yasmani, 06/10); detalle de implementacion abierto |
| Si el embedding-service devuelve puntuaciones | **RESUELTO 06/10**: las calcula y las descarta con `_`. Recuperarlas es un cambio pequeno en 3 sitios (ver 2.3) |
| Filtro de categoria dentro de la busqueda | **RESUELTO 06/10**: ya existe en la ruta outfit via `_category_map`; E5 se resuelve extendiendolo, no construyendolo (ver 2.4 y 12.1) |
