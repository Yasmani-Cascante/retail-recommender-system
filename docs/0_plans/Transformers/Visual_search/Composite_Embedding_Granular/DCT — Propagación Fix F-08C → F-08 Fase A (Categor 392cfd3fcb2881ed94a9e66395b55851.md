# DCT — Propagación Fix F-08C → F-08 Fase A (Category Expansion Turn 1) — 03/07/2026

**Fecha:** 03/07/2026

**Archivo modificado:** `src/api/core/mcp_conversation_handler.py`

**Sesión relacionada:** continuación de la sesión de cold-start/visual-search (30/06–03/07/2026)

**DCTs de referencia:** [DCT — F-08 Visual Intelligence (FashionSigLIP) — Cierre 01/06/2026], [DCT — Fix F-08C Visual Diversification (Accesorios) — 16/06/2026]

---

## Resumen ejecutivo

Se identificó y corrigió una brecha entre dos bloques de código casi gemelos (`F-08 Fase A` y `F-08 Fase C`) que manejan la misma clase de problema — resultados de similitud visual dominados por categorías ajenas cuando el producto ancla pertenece a una categoría con pocos vecinos visuales cercanos de su propio tipo — pero solo uno de los dos bloques había recibido el fix. El síntoma se manifestó en producción: una consulta "muéstrame artículos similares" sobre un producto de la colección AROS devolvió 8 vestidos, cero aros.

---

## Contexto — cómo se descubrió

Durante una sesión de validación de 4 consultas de prueba en el chat de producción, la consulta T3 ("Montrez-moi des produits similaires à celui-ci", sobre el producto AROS ANTONIETA HOJA TEXTURADA PLATEADO) devolvió 8 recomendaciones, todas vestidos, ninguna de la categoría del producto ancla (accesorios/aros). Screenshot del chat confirmó el síntoma visualmente: 0 de 8 resultados eran aros, con matches de 100%-79%.

Hipótesis inicial (descartada con evidencia): escasez de inventario de AROS en el catálogo. Se descartó al revisar la colección **Complementos** en Shopify: 685 productos activos repartidos en 9 tipos (BRAZALETE, ALAS DE NOVIA, AROMAS, AROS, CARTERAS, CINTURONES, CLUTCH, COLLARES, TOCADOS) — AROS por sí solo tiene varias decenas de productos, no es una categoría escasa.

---

## Causa raíz confirmada — dos bloques de código, un solo fix aplicado

El sistema tiene dos rutas de código separadas para "similitud visual", ambas dentro de `mcp_conversation_handler.py`:

|  | **F-08 Fase A** (Turn 1 — la que usó T3) | **F-08 Fase C** (Turn 2+) |
| --- | --- | --- |
| Cuándo activa | Primera consulta de la sesión (`not use_diversification`) | Consultas subsecuentes (`use_diversification=True`) |
| Filtro de categoría (antes del fix) | Estricto: `product_type == tipo exacto` | Expandido: `get_parent_categories()` — incluye hermanas (AROS+COLLARES+BRAZALETES+CLUTCH+...) |
| Fallback si `<3` candidatos (antes del fix) | Abandona el filtro **por completo** → pool crudo sin restricción | Rellena restringido a categorías hermanas — nunca mezcla con vestidos |
| Fix del 16/06/2026 aplicado | ❌ No (hasta esta sesión) | ✅ Sí |

El DCT del 16/06/2026 ("Fix F-08C Visual Diversification") documentó y corrigió exactamente este síntoma para AROS — pero el fix solo se aplicó al bloque de Turn 2+ (F-08C). Como T3 fue el primer mensaje de una sesión nueva (`Created MCP conversation context ... turns: 0` en los logs), pasó por Fase A, que nunca recibió el mismo fix.

**Evidencia del log exacto de T3:**

```
F-08 visual_similarity: 8 productos (cat='AROS', pool=30, filtered=1)
```

Solo 1 de los 30 vecinos visuales más cercanos era AROS. Con el código anterior, `len(_f08_same_cat)=1 < 3` → el filtro se abandonaba por completo → los 8 resultados finales venían del pool crudo, dominado por vestidos (29 de 30 vecinos).

---

## Fix aplicado

**Alcance deliberadamente acotado:** se portó SOLO la expansión a categorías hermanas (el fix original del 16/06). El mecanismo de relleno con `smart_fallback` restringido (sprint del 17/06, posterior y más complejo) **no se portó** en esta sesión — queda como mejora incremental a evaluar si la expansión de categorías por sí sola resulta insuficiente.

### Cambios en `mcp_conversation_handler.py` (bloque F-08 Fase A)

**1. Expansión a categorías hermanas** (nuevo bloque, replica el patrón ya validado de F-08C):

```python
_f08_expanded_cats = [_f08_type_upper] if _f08_type_upper else []
if _f08_type_upper:
    try:
        from src.recommenders.improved_fallback_exclude_seen import (
            get_parent_categories as _f08_get_parent_categories,
        )
        _f08_parent_map = _f08_get_parent_categories()
        _f08_siblings = next(
            (subs for subs in _f08_parent_map.values()
             if _f08_type_upper in [s.upper() for s in subs]),
            None,
        )
        if _f08_siblings:
            _f08_expanded_cats = [s.upper() for s in _f08_siblings]
            logger.info(f"F-08 category expansion: {_f08_type_upper!r} -> {_f08_expanded_cats} ...")
    except Exception as _f08_expand_err:
        _f08_expanded_cats = [_f08_type_upper] if _f08_type_upper else []
        logger.debug(f"F-08 category expansion failed (using exact type): {_f08_expand_err}")
```

**2. Filtro contra el set expandido en vez del tipo exacto:**

```python
_f08_same_cat = [
    pid for pid in _f08_visual_ids
    if str(pid) != _f08_pid
    and (
        not _f08_expanded_cats
        or _f08_tfidf.id_index.get(str(pid), {}).get("product_type", "").upper() in _f08_expanded_cats
    )
]
```

**3. Eliminado el fallback destructivo** — ya NO se abandona el filtro por completo si hay `<3` candidatos:

```python
# ANTES: _f08_ids_to_use = _f08_same_cat if len(_f08_same_cat) >= 3 else [pool crudo sin filtro]
# DESPUÉS:
_f08_ids_to_use = _f08_same_cat  # usa lo que haya dentro de las hermanas, nunca mezcla ajenas
```

**4. Red de seguridad si 0 candidatos ni siquiera en categorías hermanas:** no retorna temprano → cae al fallback estándar (`hybrid_recommender.get_recommendations`), mismo patrón que F-08C.

### Detalle de scoping — bug ya conocido, evitado a propósito

`get_parent_categories` está importado en el código **solo** dentro del bloque `if use_diversification:` (Fase C). Python trata cualquier nombre importado en una rama de una función como local a **toda** la función — en Turn 1 esa rama nunca ejecuta, así que usar `get_parent_categories` directamente en Fase A habría lanzado `UnboundLocalError`, exactamente el mismo bug ya documentado y corregido el 18/06/2026 para `normalize_recommendation_dict` (comentario `BUG-REFACTOR-1` en el propio código). El fix de esta sesión incluye un **import lazy local** dentro del bloque de Fase A, replicando ese mismo patrón defensivo ya validado.

---

## Qué NO se tocó

- El bloque F-08C (Turn 2+) — intacto, sigue funcionando exactamente igual.
- El mecanismo de relleno con `smart_fallback` restringido — evaluado y descartado para esta sesión por alcance; ver sección "Próximos pasos".
- El embedding-service — sin cambios.

---

## Log esperado en producción tras el deploy

**Caso AROS (el que falló en T3):**

```
F-08 category expansion: 'AROS' -> ['AROS', 'COLLARES', 'BRAZALETES', 'CLUTCH', 'CINTURONES', 'CARTERAS', 'TOCADOS', 'BRALETTES'] (8 types from parent group)
F-08 visual_similarity: N productos (cat='AROS', expanded_cats=[...8 tipos...], pool=30, filtered=M)
```

Donde `M` ahora cuenta candidatos de cualquiera de las 8 categorías hermanas, no solo AROS exacto.

**Caso VESTIDOS (categoría grande, no debería cambiar de comportamiento):** si `VESTIDOS CORTOS` no tiene hermanas registradas en `get_parent_categories()`, `_f08_expanded_cats` cae a `[tipo exacto]` — comportamiento idéntico al actual, sin regresión.

---

## Validación pendiente (próxima sesión)

1. Deploy del monolito con este cambio.
2. Repetir la consulta T3 exacta ("similar a Aros Antonieta", Turn 1 de sesión nueva) y confirmar en logs `F-08 category expansion` + verificar que los resultados ahora incluyen accesorios en vez de solo vestidos.
3. Confirmar que consultas sobre VESTIDOS (categoría grande) no muestran ninguna regresión de comportamiento.
4. Validar el caso límite: producto de categoría sin padre en `get_parent_categories()` — debe degradar exactamente al comportamiento anterior (tipo exacto).

---

## Próximos pasos — complementarios, no excluyentes

Este fix ataca el **síntoma de mezcla de categorías** en el filtrado post-búsqueda. La causa raíz más profunda —el embedding visual del producto AROS está dominado por el vestido de la foto principal, no por el arete— sigue sin resolverse. Ambos fixes son complementarios:

- **Este fix (aplicado):** aunque el pool de 30 vecinos visuales siga teniendo pocos AROS reales, el filtro ya no permite mezclar con vestidos — mostrará menos resultados si hace falta, pero todos relevantes.
- **Próximo fix (planificado, ver documento de implementación separado):** indexar la imagen de detalle (2ª foto de la galería) en vez de la imagen principal para productos de categorías de accesorios pequeños — mejora la calidad del pool de 30 desde el origen, en vez de solo filtrar mejor lo que ya hay.

Ver plan de implementación completo: `docs/0_plans/Transformers/Visual_search/Indexacion_Imagen_Detalle_Accesorios/Plan_de_Implementacion_03072026.md`

---

## Aprendizaje técnico

Cuando dos bloques de código resuelven el mismo problema de forma casi idéntica pero en contextos distintos (aquí: Turn 1 vs Turn 2+), un fix aplicado a uno de los dos puede dar una falsa sensación de "problema resuelto" si las pruebas de validación solo ejercitan la ruta ya corregida — el DCT del 16/06 fue validado explícitamente con consultas de Turn 2+, sin que nadie notara que Turn 1 (la interacción más común, primer contacto de cualquier usuario nuevo) seguía roto. Vale la pena, al cerrar un fix de este tipo, preguntarse explícitamente: **¿existe otro camino de código que resuelva el mismo problema y que debería recibir el mismo fix?**

---

## Continuación de sesión — Fase 0 (auditoría) + descubrimiento F-08B (03/07/2026)

Esta sección documenta dos hallazgos adicionales de la misma sesión: (1) el resultado de la Fase 0 del plan de indexación de imagen de detalle — la hipótesis no se sostuvo, y (2) un problema arquitectónico distinto encontrado por observación directa de Yasmani en el endpoint de outfit completion (F-08B).

---

## Hallazgo 1 — Fase 0 del plan de indexación de imagen de detalle: hipótesis refutada

### Contexto

Como primer paso del plan `Indexacion_Imagen_Detalle_Accesorios/Plan_de_Implementacion_03072026.md`, se ejecutó el script de auditoría `audit_accessory_images.py` sobre las 9 categorías de la colección Complementos, imprimiendo `images[0]` e `images[1]` de una muestra de productos por categoría. Yasmani revisó varios enlaces manualmente.

### Resultado: la hipótesis "images[1] = imagen de detalle" NO se sostiene de forma general

**Evidencia decisiva — patrones en los nombres de archivo:**

Para `CARTERAS`, los 3 ejemplos de la muestra mostraron que **ambas** imágenes (`[0]` y `[1]`) del mismo producto comparten el mismo prefijo de nombre de archivo, literalmente el nombre de un vestido:

```
Bolso Indio Aditi Flores Dorado:
  [0] VESTIDOVALENTINAVERDE3.jpg
  [1] VESTIDOVALENTINAVERDE6.jpg

Bolso Indio Aditi Flores Negro/Dorado:
  [0] VESTIDOFORMALNEGRO14.jpg
  [1] VESTIDOFORMALNEGRO15.jpg

Bolso Indio Amara Terciopelo Dorado:
  [0] VESTIDOSTRAPLESSCELESTE3.jpg
  [1] VESTIDOSTRAPLESSCELESTE1.jpg
```

Al menos 1 de 3 ejemplos de `BRAZALETES` mostró el mismo patrón (`VESTIDOROJO5` / `VESTIDOROJO4`).

**Interpretación:** esto no es ambigüedad de contenido — es el nombre de archivo que el fotógrafo/agencia le puso a la sesión, indicando que **la galería completa de ese producto fue organizada alrededor de un vestido/outfit**, no del accesorio. No existe ningún plano de detalle en la galería para estos productos — intercambiar el índice de imagen no puede resolver algo que no existe en el catálogo.

**Resumen por categoría:**

| Categoría | Señal del nombre de archivo | Conclusión |
| --- | --- | --- |
| CARTERAS | 3 de 3 ejemplos con ambas imágenes `VESTIDO*`-named | Sin detalle disponible — swap no ayudaría |
| BRAZALETES | 1 de 3 ejemplos con ambas imágenes `VESTIDO*`-named | Mezcla — no generalizable |
| COLLARES | Nomenclatura `COLLAR9/COLLAR10` — coherente con foco en el producto | Señal positiva, pero no garantiza mejora |
| AROS, TOCADOS, CINTURONES | Nomenclatura numérica/hash genérica, sin señal de contenido | Sin forma de saber sin inspección visual caso por caso |

### Decisión: NO proceder con el swap de índice de imagen como estaba planificado

Aplicar el heurístico "usar siempre `images[1]`" de forma general sería inútil para varias categorías (CARTERAS, parte de BRAZALETES) y no justifica el costo de un rebuild completo (~25-30 min) sin garantía de mejora. La Fase 1-3 del plan original **se pausan**.

### Camino alternativo — 3 opciones evaluadas

- **Opción A (recomendada, prioridad):** portar el mecanismo de relleno con `smart_fallback` restringido a categorías hermanas (el sprint del 17/06/2026, deliberadamente NO portado en el fix de F-08 Fase A de esta sesión). Dado que la calidad del embedding para varias categorías de accesorios es estructuralmente limitada por la fotografía disponible (no por código), este mecanismo se vuelve la defensa más robusta: garantiza que el usuario nunca vea mezcla de categorías, independientemente de la causa raíz fotográfica.
- **Opción B (no recomendada como primer paso):** curaduría manual por producto — no escala a ~700 productos.
- **Opción C (fuera de ingeniería):** reportar al equipo de contenido/fotografía que ciertas categorías de accesorios (CARTERAS, BRAZALETES) no tienen ningún plano de producto aislado en su galería — es un problema de catálogo, no de código.

---

## Hallazgo 2 — F-08B (outfit completion) nunca lee la intención específica del usuario

### Contexto — cómo se descubrió

Yasmani realizó 5 consultas de prueba de "completamiento de outfit" y observó que consultas que pedían explícitamente una categoría específica (ej. *"¿Qué accesorios combinan con este vestido?"*) devolvían de todos modos vestidos, tops, enteritos y outerwear — categorías que el usuario no pidió.

### Causa raíz confirmada en código — `mcp_conversation_handler.py`, bloque F-08 Fase B

```python
_b08_own_cat = _B08_TYPE_TO_CAT.get(_b08_ptype, "")
_b08_target_cats = [
    c for c in ["dress", "top", "accessory", "bag", "enterito", "outerwear"]
    if c != _b08_own_cat   # ← SOLO excluye la categoría del producto ancla
]
```

`_b08_target_cats` es una **lista fija**, construida únicamente a partir de la categoría del producto que el usuario está viendo (para excluir la categoría propia) — **nunca lee `conversation_query`** (el texto real de lo que el usuario pidió). El resultado: da igual si el usuario escribe "completa el outfit" (petición amplia) o "¿qué accesorios combinan?" (petición específica de una sola categoría) — ambas activan `sub_intent == "outfit_completion"` y ambas disparan la misma búsqueda de 5-6 categorías.

**Verificación exacta contra los 5 casos de prueba de Yasmani:**

| Consulta | Categoría del producto ancla | Categorías devueltas | Coincide con la fórmula |
| --- | --- | --- | --- |
| "Completa el outfit..." | dress | `[dress, accessory, bag, enterito, outerwear]` | ✅ |
| "Que combina con esto..." | top | `[top, accessory, bag, enterito, outerwear]` | ✅ excluye top |
| "Quels accessoires vont avec cette robe?" | dress | `[top, accessory, bag, enterito, outerwear]` | ✅ excluye dress, pero incluye 4 categorías no pedidas |
| "Que accesorios combinan con esto?" | (sin categoría reconocida) | `[dress, top, accessory, bag, enterito, outerwear]` | ✅ lista completa |
| "Busco algo que combine con esto" | enterito | resultado real: 8/8 fueron enteritos (ver Hallazgo 3) | ⚠️ anómalo — ver más abajo |

### Confirmación adicional: el equipo ya resolvió un problema similar, pero solo en la ruta de fallback

Existe un segundo bloque, **F-08 Fase B.2**, que solo se activa como fallback (`VISUAL_SEARCH_ENABLED=false` o cuando B falla), con un mapeo curado por tipo de producto:

```python
_OUTFIT_COMPLEMENT_MAP = {
    "VESTIDOS LARGOS": ["AROS", "COLLARES", "CLUTCH", "TOCADOS", "CINTURONES"],
    "VESTIDOS CORTOS": ["AROS", "CLUTCH", "CINTURONES", "BRAZALETES"],
    "KIMONOS":         ["AROS", "COLLARES", "CLUTCH", "CINTURONES", "BRAZALETES"],
    ...
}
```

El propio comentario del código confirma que este es un fix anterior para un síntoma relacionado: *"Sin este fix: 'quelque chose qui va avec ça' → más kimonos."* — pero ni siquiera este bloque lee el texto de la consulta; usa un mapeo fijo por tipo de producto, sin distinguir "outfit completo" de "solo accesorios".

### Fix propuesto (no aplicado aún — pendiente de decisión y priorización)

Reutilizar `extract_categories_from_query()` (ya usada en F-08C y en el bloque "Standard recommendations", ver `mcp_conversation_handler.py`) dentro de F-08B, **antes** de construir `_b08_target_cats`:

1. Si `extract_categories_from_query(conversation_query, get_concrete_categories())` detecta una categoría explícita en el texto (ej. "accesorios" → tipos Shopify AROS/COLLARES/etc.), mapear esos tipos a su categoría de outfit vía `SHOPIFY_TYPE_TO_OUTFIT_CATEGORY` (ya definido en `visual_retriever.py`) y usar **solo esa** como `target_categories`.
2. Si no se detecta ninguna categoría explícita (consulta genuinamente abierta, ej. "completa el outfit"), mantener el comportamiento actual (lista completa de categorías) — sigue siendo correcto para ese caso.

No se implementó en esta sesión — queda pendiente de priorización junto con el Hallazgo 1.

---

## Hallazgo 3 — Anomalía en Q5, no diagnosticada (requiere investigación separada)

La consulta "busco algo que combine con esto" sobre un producto de categoría `enterito` devolvió, según observación de Yasmani, **exclusivamente más enteritos** — a pesar de que `_b08_own_cat = "enterito"` debería excluir esa categoría de `_b08_target_cats`. No hay evidencia de logs suficiente en esta sesión para diagnosticar la causa exacta (posibles hipótesis sin confirmar: el `category_map` del embedding-service confunde "dress" y "enterito" por ser prendas visualmente similares de una sola pieza; o agotamiento de pools que cae a otro mecanismo de relleno). **Se documenta como hallazgo abierto, no se investiga en esta sesión** — requiere logs frescos dedicados específicamente a este caso.

---

## Estado consolidado de los 3 hallazgos de esta sesión (pendientes de priorizar)

| # | Hallazgo | Endpoint/bloque afectado | Estado |
| --- | --- | --- | --- |
| 1 | Indexación de imagen dominada por vestido en accesorios | `search-by-id` (F-08/F-08C), pipeline de indexación | Diagnosticado — plan de imagen de detalle **pausado** (hipótesis refutada en Fase 0); pivote a Opción A (relleno restringido) recomendado |
| 2 | F-08B nunca lee la categoría específica pedida por el usuario | `/search-outfit` (F-08 Fase B, outfit completion) | Diagnosticado con evidencia exacta de código; fix propuesto, no implementado |
| 3 | Q5: resultado 100% mismo-categoría en vez de complementaria | `/search-outfit` (F-08 Fase B) | Anomalía observada, causa no confirmada — requiere sesión de investigación dedicada con logs nuevos |

**Próximo paso:** decidir el orden de trabajo entre estos 3 hallazgos más la Opción A del Hallazgo 1 (portar el relleno restringido de F-08C), en la próxima sesión.

---

## Validación final de F-08 Fase A — Cierre exitoso (06/07/2026)

Esta sección cierra el ciclo de validación de la Opción A del Hallazgo 1 (propagación del fix F-08C → F-08 Fase A), abierto varias sesiones atrás.

### Problema de validación resuelto: cómo aislar Turn 1 de verdad

Sesiones anteriores no lograban validar Fase A porque cualquier secuencia normal de clics en el widget (subir foto → similar a este) terminaba aterrizando en F-08C (Turn 2+), no en Fase A (Turn 1) — sin quedar claro por qué. Se investigó el código de `conversation_state_manager.py` para resolver la ambigüedad con certeza, en vez de asumir.

**Mecanismo confirmado:**

- `total_turns` se incrementa únicamente dentro de `add_conversation_turn_simple()` / `_add_conversation_turn_enterprise()`, llamadas **después** de procesar cada consulta que pasa por `mcp_conversation_handler.py::get_base_recommendations()`.
- `get_or_create_session()` crea contexto con `total_turns=0` si el `session_id` es nuevo.
- La decisión Fase A vs F-08C se basa en el valor de `total_turns` **al inicio** de cada request (antes de incrementarlo).

**Metodología de prueba diseñada:** abrir una ventana de incógnito (sesión realmente nueva) y hacer clic en "similar a este producto" (ícono de lupa) como primera acción del usuario, sin escribir texto ni subir foto antes.

### Resultado — validado con logs reales, sesión `widget_session_1783314458939_uatngeum7`

```
05:09:35  Visual search: 8 results                              ← T1, foto subida
05:10:03  Created MCP conversation context                       ← sesión genuinamente nueva
05:10:03  MCP context loaded: turns=0                             ← Turn 1 confirmado
05:10:04  search_by_product_id: product_id=9978624672053          ← Aros Antonieta (el mismo producto del hallazgo original)
05:10:04  F-08 category expansion: 'AROS' -> ['AROS', 'COLLARES', 'BRAZALETES', 'CLUTCH', 'CINTURONES', 'CARTERAS', 'TOCADOS', 'BRALETTES']
05:10:04  F-08 visual_partial_plus_fill: 8 productos totales (visual=1, fill=7, needed_fill=7, cats=[8 tipos])
```

**Tres confirmaciones simultáneas:**

1. Subir una foto (`visual_search()`, endpoint separado en `visual_search_router.py`) **no incrementa** `total_turns` — confirmado empíricamente (turns=0 después de T1).
2. El saludo inicial del widget al cargar la página **tampoco** incrementa `total_turns` — de lo contrario habríamos visto turns≥1 en este punto.
3. **Ambos fixes de F-08 Fase A están desplegados y funcionando exactamente como se diseñaron**: el mismo producto (Aros Antonieta) que semanas atrás devolvía 8 vestidos y 0 aros en su primera interacción, ahora devuelve 8 accesorios reales (1 visual + 7 de relleno restringido a categorías hermanas), 0 vestidos.

### Estado final

| Fix | Estado |
| --- | --- |
| Expansión a categorías hermanas (F-08 Fase A) | ✅ Validado en producción, Turn 1 real |
| Relleno restringido con `smart_fallback` (F-08 Fase A) | ✅ Validado en producción, Turn 1 real |

Con esto se cierra formalmente la Opción A del Hallazgo 1, abierta el 03/07/2026.

---

## Nueva investigación: clasificación correcta de "BRALETTES" (06/07/2026)

Durante la sesión de validación se identificó una inconsistencia real: `get_parent_categories()["ACCESSORIES"]` incluye `"BRALETTES"` como hermana de AROS/COLLARES/etc., pero:

- `visual_retriever.py::SHOPIFY_TYPE_TO_OUTFIT_CATEGORY` clasifica `BRALETTES` como `"top"` (prenda), no accesorio.
- La colección real de Shopify "Complementos" (confirmada por captura de pantalla, 9 tipos: BRAZALETE, ALAS DE NOVIA, AROMAS, AROS, CARTERAS, CINTURONES, CLUTCH, COLLARES, TOCADOS) **no incluye BRALETTES en absoluto**.

### Investigación de estándar de industria (antes de decidir)

Se consultó documentación real de e-commerce de moda (taxonomía de Google Shopping Merchant Center, guías de categorización de retail) para no basar la decisión solo en comparación interna de código:

- La taxonomía estándar de e-commerce de moda separa `Clothing`, `Accessories`, `Footwear`, y `Undergarments & Lingerie` como ramas de nivel superior distintas.
- Google Shopping clasifica bralettes específicamente bajo `Apparel & Accessories > Clothing > Underwear & Socks > Bras` (categoría 214) — **nunca** bajo `Accessories`.
- La distinción de fondo: accesorios (joyería, bolsos, cinturones, tocados) **complementan** una prenda ya puesta; un bralette **es la prenda** que cubre el torso — funcionalmente reemplaza a un top.

**Conclusión:** `visual_retriever.py` tiene la clasificación correcta (`BRALETTES → "top"`). `get_parent_categories()["ACCESSORIES"]` está equivocado al incluirlo — no es una diferencia de granularidad legítima, es una clasificación incorrecta según estándares reales de la industria.

### Discrepancias adicionales confirmadas contra la colección real de Shopify

| Tipo | En Shopify "Complementos" | En `get_parent_categories()["ACCESSORIES"]` | Diagnóstico |
| --- | --- | --- | --- |
| `BRAZALETE` (singular, 1 producto) | ✅ | ❌ ausente | Gap real — nunca expande a hermanas |
| `ALAS DE NOVIA` | ✅ | ❌ ausente | Gap real — nunca expande a hermanas |
| `AROMAS` | ✅ | ❌ ausente (y en `NON_FASHION_CATEGORIES_UPPER`) | Exclusión deliberada y correcta (no es prenda vestible) |
| `BRALETTES` | ❌ no pertenece a Complementos | ✅ incluido | Inconsistencia real — a corregir |

### Fix a aplicar (siguiente paso inmediato)

En `src/recommenders/improved_fallback_exclude_seen.py`, actualizar `CATEGORY_KEYWORDS["ACCESSORIES"]["subcategories"]`:

- Quitar `"BRALETTES"`.
- Añadir `"BRAZALETE"` (singular) y `"ALAS DE NOVIA"`.

Resultado esperado: 9 subcategorías, alineadas exactamente con la colección real "Complementos" de Shopify, menos AROMAS (excluido correctamente por no ser vestible).

---

## Sesión de continuación — Hallazgo 2 (F-08B) y Hallazgo T8 (ranking F-08C) — 06/07/2026

Esta sección documenta dos fixes adicionales aplicados en la misma línea de trabajo, más los gaps menores identificados pero deliberadamente no resueltos hoy (para no ampliar el alcance de cada cambio puntual).

---

## Hallazgo 2 — F-08B ahora lee la categoría específica pedida por el usuario

### Diagnóstico (recordatorio, ya confirmado en sesión anterior con evidencia real)

```python
# ANTES:
_b08_target_cats = [
    c for c in ["dress", "top", "accessory", "bag", "enterito", "outerwear"]
    if c != _b08_own_cat
]
```

`_b08_target_cats` era siempre la lista fija de 6 categorías (menos la categoría propia del producto ancla), **sin leer nunca `conversation_query`**. Evidencia real (05/07/2026): *"¿Qué accesorios combinan con este vestido?"* devolvió `categories=['top', 'accessory', 'bag', 'enterito', 'outerwear']` — 4 categorías que el usuario nunca pidió, mezcladas con los accesorios que sí pidió.

### Fix aplicado — `mcp_conversation_handler.py`, bloque F-08 Fase B

Antes de construir la lista fija, intenta detectar una categoría explícita en el texto vía `extract_categories_from_query()` (reutilizando la misma función ya validada en F-08C), mapea los tipos Shopify detectados a su bucket de outfit-category, y usa **solo esos** como `target_categories`. Si no detecta nada (consulta genérica tipo "completa el outfit"), mantiene el comportamiento amplio actual sin cambios.

```python
_B08_SHOPIFY_TO_OUTFIT_CAT = {
    "AROS": "accessory", "COLLARES": "accessory", "BRAZALETES": "accessory",
    "BRAZALETE": "accessory", "CINTURONES": "accessory", "TOCADOS": "accessory",
    "ALAS DE NOVIA": "accessory", "CARTERAS": "bag", "CLUTCH": "bag",
    "VESTIDOS CORTOS": "dress", "VESTIDOS LARGOS": "dress", "VESTIDOS MIDIS": "dress",
    "ENTERITOS CORTOS": "enterito", "ENTERITOS LARGOS": "enterito",
    "TOPS": "top", "BRALETTES": "top", "PANTALONES": "bottom", "FALDAS": "bottom",
    "CAPAS BORDADAS": "outerwear", "CAPAS GASA": "outerwear", "KIMONOS": "outerwear",
}
# ... extract_categories_from_query(conversation_query, get_concrete_categories())
# ... mapea cada tipo detectado a su bucket, descarta _b08_own_cat, usa el resultado
# si no está vacío; si no, mantiene la lista fija de siempre.
```

Import lazy de `extract_categories_from_query`/`get_concrete_categories` dentro del propio try de F-08B — mismo patrón defensivo que `get_parent_categories` en F-08 Fase A (F-08B puede activarse en Turn 1 también, donde el import a nivel de `if use_diversification:` nunca ejecuta).

### Log esperado tras el deploy

```
F-08B query category detected: ['AROS', 'COLLARES', ...] -> ['accessory', 'bag'] (narrowing target_categories)
F-08B outfit_completion: 8 productos (categories=['accessory', 'bag'], pid='...')
```

### Reflexión posterior — `{accessory, bag}` no es un error, pero expone una limitación más profunda (ya identificada antes)

Se trazó `extract_categories_from_query()` línea por línea contra *"¿Qué accesorios combinan con este vestido?"*: detecta los 9 tipos de Complementos (specificity 0.5) **y también** "vestido" (specificity 0.1, penalizado por el marcador relacional *"combinan con este"*, pero no eliminado de la lista). El `.discard(_b08_own_cat)` del fix quita "dress" porque es la categoría del producto ancla. Resultado: `{accessory, bag}` — **correcto**, dado que el usuario pidió la palabra genérica "accesorios" y en la taxonomía real de esta tienda (colección Complementos) los bolsos sí pertenecen a esa familia.

**El gap real es un nivel más abajo**: `search_outfit_by_image()` usa **un solo prompt de texto genérico por bucket** de outfit-category (`CATEGORY_TEXT_PROMPTS["accessory"]` mezcla aros/collares/brazaletes/cinturones/tocados en una sola frase). Si el usuario pidiera algo más específico ("¿qué aros combinan?"), el sistema detectaría `AROS` correctamente pero lo colapsaría igual al bucket genérico `"accessory"` — sin forma de pedir específicamente "aros" al Composite Embedding. Es el mismo gap ya identificado en la investigación de Composite Embedding/FashionSigLIP de sesiones anteriores — pendiente de plan de implementación.

---

## Hallazgo T8 — F-08C no priorizaba el tipo exacto del producto ancla en el camino feliz

### Diagnóstico (recordatorio, evidencia real de sesión 05/07/2026)

Clic en "similar a este" sobre un **COLLAR** (categoría pequeña, ~22 productos) devolvió 5 Aros + 2 Chocker + 1 Collar real. Log: `F-08C visual_diversification: 8 productos (pool=50, cats=[8 tipos], candidates=49)` — camino feliz (≥8 candidatos), sin necesidad de relleno. El problema: `_c08_candidates[:n_recommendations]` cortaba por **orden de similitud visual pura**, sin ningún peso hacia el tipo exacto del producto ancla frente a sus hermanas numéricamente más grandes (AROS=524 productos vs COLLARES=22).

### Fix aplicado — `mcp_conversation_handler.py`, bloque F-08 Fase C

Dos inserciones:

**1.** Variable `_c08_anchor_type_for_ranking = None` por defecto, seteada **solo** dentro de la rama de expansión por contexto (`if not _c08_query_cats:` → el usuario no pidió una categoría explícita por texto, solo "similar a este"):

```python
if _c08_ctx_type:
    _c08_anchor_type_for_ranking = _c08_ctx_type.upper()
    # ... resto de la expansión a hermanas, sin cambios
```

**2.** Partición estable del pool justo antes de cortar a `n_recommendations`, solo si `_c08_anchor_type_for_ranking` está seteado:

```python
if _c08_anchor_type_for_ranking:
    _c08_candidates = sorted(
        _c08_candidates,
        key=lambda pid: 0 if (
            _c08_tfidf.id_index.get(str(pid), {}).get("product_type", "").upper()
            == _c08_anchor_type_for_ranking
        ) else 1,
    )
```

**Alcance deliberado**: la priorización **solo** aplica cuando la categoría vino del contexto del producto (el usuario no especificó nada por texto). Si el usuario pidió explícitamente otra categoría por texto (Turn 2+, ej. "muéstrame collares" viendo un producto AROS), `_c08_anchor_type_for_ranking` permanece `None` — no tendría sentido priorizar el tipo del producto ancla en contra de lo que el usuario pidió explícitamente.

**Mecanismo**: partición estable (Python `sorted()` es stable) — candidatos del tipo exacto primero (preservando su orden interno por similitud), luego las hermanas (también preservando orden interno). No es un re-ranking por score nuevo — es una partición en dos grupos que preserva la calidad de similitud visual dentro de cada grupo.

---

## Gaps menores identificados pero NO resueltos hoy (documentados para sesión futura)

Estos tres gaps se identificaron durante el trabajo de hoy pero se dejaron deliberadamente fuera de alcance para no ampliar cada cambio puntual. Se documentan aquí para no perderlos:

### Gap A — `extract_categories_from_query()` no reconoce "BRAZALETE" (singular) como su propia categoría de texto libre

**Corrección respecto a la primera versión de esta nota** (verificado contra el archivo completo, no asumido): `"ALAS DE NOVIA"` **sí tiene** su propia entrada `"concrete"` en `CATEGORY_KEYWORDS`, con keywords propios (`"ala novia"`, `"alas novia"`, `"velo"`, `"velos"`, `"veil"`, `"veils"`) — la detección por texto libre para "alas de novia" **ya funciona correctamente**, sin gap.

El gap real y confirmado es más acotado de lo que se pensó inicialmente: **"BRAZALETE" (singular)** no tiene su propia entrada `concrete` — solo existe `"BRAZALETES"` (plural) con keywords `"brazalete"`, `"brazaletes"`, `"pulsera"`, `"pulseras"`, etc. Como la búsqueda de keywords usa `\b` (word boundary) sobre el texto normalizado, la palabra suelta "brazalete" en una consulta **sí** haría match con el keyword `"brazalete"` de la entrada `BRAZALETES` (el keyword no exige plural exacto) — así que en la práctica, decir "brazalete" en una consulta de texto **sí se detecta**, solo que se categoriza como `BRAZALETES` (la entrada concrete existente) en vez de como `BRAZALETE` (el product_type singular real de 1 producto en el catálogo). Diferencia sutil entre "detección de la palabra" (funciona) y "el producto singular específico apareciendo en resultados" (podría no aparecer si el filtro post-detección compara contra el nombre exacto `BRAZALETES` y no contra `BRAZALETE`) — pendiente de revisar con una prueba real antes de decidir si amerita corrección.

### Gap B — `_B08_TYPE_TO_CAT` (usado en F-08B) no incluye los tipos reales de Complementos

```python
_B08_TYPE_TO_CAT = {
    "vestidos cortos": "dress", ..., "accesorios": "accessory", ...
}
```

Esta tabla, usada para calcular `_b08_own_cat` (la categoría del producto ancla que se excluye de `target_categories`), solo tiene una entrada genérica `"accesorios": "accessory"` que **nunca calza** con ningún `product_type` real del catálogo (los productos reales son `"AROS"`, `"COLLARES"`, etc. — no literalmente `"accesorios"`). Esto significa que `_b08_own_cat` probablemente queda vacío (`""`) para casi cualquier producto de accesorios real visto como ancla, y por lo tanto la exclusión de "no recomendar la propia categoría del producto ancla" no funciona bien para esos casos específicos. Bug pequeño, independiente del Hallazgo 2 ya corregido.

### Gap C — Composite Embedding sin granularidad por tipo Shopify específico

Ya descrito arriba en la reflexión de `{accessory, bag}`: `CATEGORY_TEXT_PROMPTS` en `visual_retriever.py` solo tiene un prompt de texto por cada uno de los 9 buckets de outfit-category — no existe forma de pedir "aros específicamente" al Composite Embedding, solo "accesorios en general". Mismo gap ya anotado en la investigación de FashionSigLIP de sesiones anteriores.

---

## Estado consolidado actualizado

| # | Ítem |
| --- | --- |
| Fix F-08 Fase A (expansión + relleno) | ✅ Validado en producción con logs reales |
| Corrección BRALETTES → top / BRAZALETE + ALAS DE NOVIA → ACCESSORIES | ✅ Aplicado |
| Hallazgo 2 — F-08B lee categoría específica de la consulta | ✅ Aplicado hoy |
| Hallazgo T8 — F-08C prioriza tipo exacto en camino feliz | ✅ Aplicado hoy |
| Gap A — keywords de texto libre para BRAZALETE/ALAS DE NOVIA | 🔵 Pendiente de verificar/resolver |
| Gap B — `_B08_TYPE_TO_CAT` incompleto | 🔵 Pendiente |
| Gap C — Composite Embedding sin granularidad por tipo específico | 🔵 Pendiente — mismo plan que la investigación de FashionSigLIP |
| Deploy + validación conjunta de Hallazgo 2 + T8 + BRALETTES | 🔵 Pendiente |
| Plan de Composite Embedding granular (search-by-id y/o search-outfit) | 🔵 Pendiente de escribir |

---

## Archivos modificados en esta sesión de continuación

| Archivo | Cambios |
| --- | --- |
| `src/api/core/mcp_conversation_handler.py` | Hallazgo 2 (bloque F-08 Fase B) + Hallazgo T8 (bloque F-08 Fase C, 2 inserciones) |
| `src/recommenders/improved_fallback_exclude_seen.py` | Corrección BRALETTES/BRAZALETE/ALAS DE NOVIA (sesión anterior, ya documentada arriba) |

---

## Cierre de sesión — Validación de los 5 casos + Fix del keep-alive GPT-4o-mini (11/07/2026)

### Validación de los 5 casos pendientes (revisión `retail-recommender-00255-flg`)

Cruzando logs reales con captura de pantalla de la conversación completa:

| Caso | Resultado | Evidencia exacta |
| --- | --- | --- |
| **1 — Fix BRALETTES/BRAZALETE/ALAS DE NOVIA** | ✅ Confirmado | `F-08C category expansion: 'COLLARES' -> ['AROS', 'COLLARES', 'BRAZALETES', 'BRAZALETE', 'CLUTCH', 'CINTURONES', 'CARTERAS', 'TOCADOS', 'ALAS DE NOVIA']` — 9 tipos, sin BRALETTES |
| **2 — F-08B narrow "accesorios"** | ⚪ No ejercitado esta ronda | La frase usada ("Muéstrame accesorios similares") activó F-08C (similar-a-este) por la palabra "similares", no F-08B. Validado correctamente en sesión anterior (06/07) con la frase "¿Qué accesorios combinan...?" |
| **3 — Control de regresión** | ✅ Confirmado | Botón "Completar outfit" → sin log F-08B después, comportamiento amplio intacto, sin regresión |
| **4 — Gap ZAPATOS** | ✅ Confirmado con evidencia real | `🎯 Single category detected from query: 'ZAPATOS'` seguido de `F-08B outfit_completion: categories=['top','accessory','bag','enterito','outerwear']` (fallback amplio) — `extract_categories_from_query()` detecta "ZAPATOS" correctamente, pero `_B08_SHOPIFY_TO_OUTFIT_CAT` no tiene esa clave, así que cae en silencio al comportamiento genérico |
| **5 — Ranking T8 (tipo exacto vs hermanas numerosas)** | ✅ Confirmado, visual + logs | "Similar a este" sobre un Collar devolvió 6 Collar/Chocker + 2 Aros (antes del fix: 5 Aros + 2 Chocker + 1 Collar). Log: `F-08C visual_diversification: candidates=46` (camino feliz, pool abundante) |

### Gap adicional confirmado — pendiente para próxima sesión

`_B08_SHOPIFY_TO_OUTFIT_CAT` (el diccionario de mapeo Shopify→outfit-bucket usado en el fix de Hallazgo 2) no incluye `ZAPATOS → shoes` ni `CONJUNTOS FALDAS/PANTALONES → conjunto`. Cuando el usuario pide una categoría específica que no está en ese diccionario, `extract_categories_from_query()` la detecta correctamente pero el mapeo la descarta silenciosamente, cayendo al comportamiento amplio de siempre. Fix propuesto (no aplicado): añadir las entradas faltantes al diccionario.

---

## Investigación y fix — Keep-alive dedicado para GPT-4o-mini del motor conversacional

### Contexto del hallazgo

Durante la investigación del fallo de LFM (proveedor único caído en OpenRouter, 404 "No endpoints found", externo y persistente desde el 10/07), se descubrió que el **fallback a GPT-4o-mini también fallaba** en el motor conversacional (`mcp_personalization_engine.py`) — 4 de 4 timeouts a los 8.0s en la sesión de prueba original.

### Descartado como causa: `embedding-service/main.py`

Revisado completo — cero relación con LLM/OpenRouter. Microservicio autocontenido (ColBERT + FashionSigLIP + FAISS), sin infraestructura compartida con las llamadas LLM del monolito.

### Causa raíz confirmada en código

`llm_client.py`: cada instancia de `UnifiedLLMClient` crea su propio `AsyncOpenAI` con su propio pool de conexiones — sin compartir nada entre instancias, aunque apunten al mismo host. `self._lfm_client` y `self._gpt4o_mini_client` (motor conversacional) son dos instancias completamente separadas.

El comentario original en `claude_config.py` asumía: *"La conexión TCP a OpenRouter ya está warm gracias al LFM keep-alive (PASO 8.7). No se necesita warm-up propio."* — **suposición arquitectónicamente incorrecta**, confirmada como falsa por el código real. El keep-alive de LFM (cada 300s) nunca mantuvo caliente la conexión de GPT-4o-mini.

Bajo uso normal (LFM funciona casi siempre), este gap pasa desapercibido porque el fallback rara vez se ejercita. Con LFM caído al 100%, cada consulta conversacional pasó a depender de una conexión fría, sin mantenimiento — de ahí los 4/4 timeouts.

### Fix aplicado — PASO 8.8 (`main_unified_redis.py`)

Mismo patrón exacto que el PASO 8.7 (LFM keep-alive), aplicado a `self._gpt4o_mini_client` del motor conversacional:

- Ping cada 300s, timeout de 15s, reutiliza el mismo `_lfm_ka_engine` ya obtenido para el keep-alive de LFM (ambos clientes viven en la misma instancia de `MCPPersonalizationEngine`).
- Shutdown limpio simétrico al de PASO 8.7.
- Independiente del keep-alive de `visual_search_router.py` (PASO 8.5e) y del de LFM (PASO 8.7) — tres clientes GPT-4o-mini/LFM distintos en el sistema, cada uno con su propio mantenimiento ahora.

### Validación con datos reales (revisión `00255-flg`)

```
✅ GPT-4o-mini MCP keep-alive background task started (interval=300s)
...
11:51:46  LFM MCP call failed (404, proveedor externo caído)
11:51:47  gpt4o_mini_fallback_ok: in=571 out=82  ← 1.6s (antes: timeout a los 8.0s)
...
11:52:52  LFM MCP call failed (404)
11:52:54  gpt4o_mini_fallback_ok: in=613 out=99  ← 1.9s (antes: timeout a los 8.0s)
```

**2 de 2 fallbacks exitosos**, con LFM fallando el 100% de las veces (confirmado como problema externo persistente, no nuestro). Comparado con la sesión anterior (10/07, sin el fix): 4 de 4 timeouts a los 8.0s.

**Dato a vigilar, no una falla:** el primer ping periódico de keep-alive (a los ~320s del arranque) tardó 14.7s — dentro del presupuesto de 15s, pero mucho más lento que lo típico (~500-700ms). Podría indicar una lentitud general de OpenRouter en este período, coincidiendo con la caída del proveedor de LFM. Monitorear en próximas sesiones.

### Estado de LFM en OpenRouter

Sigue caído (404, proveedor único) más de 24h después del primer fallo detectado. Modelo revertido correctamente a `liquid/lfm-2-24b-a2b` (sin sufijo de fecha, confirmado como el identificador correcto contra el catálogo real de OpenRouter). Fuera de nuestro control — requiere que el proveedor de Liquid en OpenRouter restablezca el servicio.

---

## Estado consolidado final de la sesión

| # | Ítem |
| --- | --- |
| Fix F-08 Fase A (expansión + relleno) | ✅ Validado en producción |
| BRALETTES/BRAZALETE/ALAS DE NOVIA | ✅ Validado (Caso 1) |
| Hallazgo 2 — F-08B lee categoría específica | ✅ Validado (sesión 06/07); gap de cobertura (ZAPATOS/CONJUNTOS) confirmado hoy (Caso 4) |
| Hallazgo T8 — prioridad de tipo exacto | ✅ Validado, visual + logs (Caso 5) |
| Keep-alive GPT-4o-mini motor conversacional (PASO 8.8) | ✅ **Implementado y validado con datos reales** |
| LFM caído en OpenRouter | 🔴 Persiste — externo, monitorear |
| Gap: `_B08_SHOPIFY_TO_OUTFIT_CAT` incompleto (ZAPATOS, CONJUNTOS) | 🔵 Pendiente próxima sesión |
| Gap: `_B08_TYPE_TO_CAT` incompleto (Gap B, sesión 06/07) | 🔵 Pendiente próxima sesión |
| Plan Composite Embedding granular (Gap C) | 🔵 Plan escrito, implementación pendiente |

---

## Sesión de cierre — Composite Embedding Granular, Fase 1 a Fase 3b (19-23/07/2026)

Esta sección documenta el cierre del plan **Composite Embedding Granular** (`docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/Plan_de_Implementacion_09072026.md`), que nace directamente del **Gap C** identificado en esta misma página (sección "Hallazgo 2 — F-08B", reflexión sobre `{accessory, bag}`). Implementa el alcance F-08/F-08C (`alpha=0.5`, reforzar el propio tipo del ancla); F-08B (`alpha=0.2`, pedir un tipo distinto) queda como Fase 1b, ver más abajo.

### Resumen ejecutivo

Implementado, desplegado y validado en producción con evidencia de logs reales. El camino tuvo un incidente serio a mitad de camino (gap de diseño que dejó el código inalcanzable ~3 días), diagnosticado con evidencia de log y corregido. Al validar, se confirmó con datos cuantificados el propio "Gap C" de esta página — ver sección final.

### Cronología

**Fase 0 (18-19/07)** — POC con 6 casos reales: confirma que se necesitan dos alphas distintos: `alpha≈0.5` para reforzar el propio tipo (uso F-08/F-08C), `alpha≈0.2` para pedir un tipo distinto (uso F-08B, Fase 1b).

**Fase 1 (19/07)** — `visual_retriever.py` (embedding-service): nuevo dict `SHOPIFY_TYPE_TEXT_PROMPTS` (9 tipos, verificado 1:1 contra `get_parent_categories()["ACCESSORIES"]`), `warmup()` extendido, nueva función `search_by_product_id_with_category_boost(product_id, boost_category, alpha=0.5, top_k=8)`. Desplegado y validado: `text_embed_cache: 18 categories pre-computed` en 2 cold starts (revisión `retail-embedding-service-00047-flj`), sin errores.

**Fase 3 (19/07)** — integración en `mcp_conversation_handler.py`: opt-in aditivo en F-08 Fase A y F-08C — si el tipo del ancla pertenece a ACCESSORIES, llama al boost con `alpha=0.5` explícito; si no, sin cambios. Lógica T8 y expansión a hermanas (documentadas arriba en esta misma página) quedaron intactas.

**Incidente (20/07)** — las 4 consultas de similitud sobre accesorios fallaban:

```
'LFM2ColBERTClient' object has no attribute 'search_by_product_id_with_category_boost'
```

**Causa raíz:** `visual_retriever.py` vive en el embedding-service (microservicio separado); el monolito solo le habla vía `LFM2ColBERTClient` (HTTP). Fase 1 agregó la función solo en el lado del embedding-service; Fase 3 hizo que el monolito la llamara — pero nunca se agregó el endpoint HTTP correspondiente ni el método cliente. El error, capturado por un `except Exception` preexistente y amplio, degradaba silenciosamente: F-08 Fase A caía a TF-IDF genérico; F-08C caía al fallback de diversificación (expansión a los 9 tipos hermanos) — produciendo resultados de "similitud" indistinguibles de un completamiento de outfit (de ahí que el LLM usara lenguaje de "complementar").

**Fase 3b (22/07)** — cerrar el círculo: nuevo endpoint `GET /v1/embed/search-by-id-with-boost` en `main.py` (embedding-service) + nuevo método `search_by_product_id_with_category_boost()` en `colbert_client.py` (monolito), mismo patrón que sus contrapartes existentes. `mcp_conversation_handler.py` no requirió cambios adicionales.

### Validación final (23/07, revisión `retail-recommender-00268-fvr`)

7 consultas de prueba. Las 3 de similitud activaron el boost correctamente, cero errores:

| Turn | Ancla (tipo) | `F-08C candidate breakdown` (pool FAISS, 50) | % mismo tipo |
| --- | --- | --- | --- |
| T2 | AROS | `{'AROS': 50}` | 100% |
| T4 | CARTERAS | `{'CARTERAS': 46, 'AROS': 3, 'BRAZALETES': 1}` | 92% |
| T6 | COLLARES | `{'COLLARES': 15, 'AROS': 26, 'BRAZALETES': 7}` | 31% |

**Composite Embedding Granular (F-08/F-08C, alpha=0.5) — CERRADO Y VALIDADO.** COLLARES notablemente más débil (31%) — consistente con el propio hallazgo de Fase 0 que ya marcaba Collar→Collares como "punto de quiebre" de alpha=0.5. Candidato a alpha por tipo en vez de global, con más datos.

### Confirmación cuantificada del "Gap C" de esta página

Las mismas 7 consultas incluyeron 3 de completamiento de outfit (F-08B, "qué accesorios combinan"):

| Turn | Ancla (tipo) | Bucket propio | Resultado final |
| --- | --- | --- | --- |
| T3 | AROS | `accessory: {'AROS': 15}` (100% mismo tipo, 0 útiles) | **1 producto** |
| T5 | CARTERAS | `bag: {'CARTERAS': 15}` (100% mismo tipo) | 8 productos |
| T7 | COLLARES | `accessory: {'COLLARES': 7, 'AROS': 8}` (mezclado) | 8 productos |

Esto es la manifestación cuantificada exacta del Gap C ya documentado arriba en esta página: `search_outfit_by_image()` usa un prompt genérico por bucket, sin forma de excluir el tipo del ancla a nivel de *retrieval* — la exclusión solo ocurre después, dejando muy pocos candidatos reales cuando el bucket propio domina (caso extremo T3: cero). **Fase 1b (alpha=0.2, ya con interfaz parametrizada desde Fase 1) es la solución directa** — pendiente de diseño de integración propio, dado que `search_outfit_by_image()` aplica alpha a nivel de bucket completo hoy, no de tipo específico.

### Otros hallazgos de esta sesión (sin relación con Composite Embedding)

- **Startup lento del monolito** (2 intentos fallidos antes de éxito, 22/07): el startup probe HTTP (documentado arriba en esta página, sección "Opción A") funcionó exactamente como se diseñó — no es un gap nuevo. LFM 404 sigue caído (externo, desde 10/07, ya documentado). **Dato nuevo:** Redis respondió con latencias de 21-39s (vs. blips de ~1s en sesiones previas) — a vigilar en el próximo deploy.
- **Aprendizaje de proceso:** cruzar el límite monolito↔microservicio es una pieza de trabajo en 3 partes (función + endpoint HTTP + método cliente), no 2 — ningún `py_compile` detecta la tercera pieza faltante porque el error solo existe en tiempo de ejecución, cruzando un proceso. Un smoke-test real end-to-end tras cualquier cambio de este tipo es obligatorio.

### Archivos modificados

| Archivo | Servicio | Cambio |
| --- | --- | --- |
| `visual_retriever.py` | embedding-service | `SHOPIFY_TYPE_TEXT_PROMPTS`, `warmup()`, `search_by_product_id_with_category_boost()` |
| `main.py` | embedding-service | Endpoint `GET /v1/embed/search-by-id-with-boost` |
| `mcp_conversation_handler.py` | monolito | Opt-in F-08 Fase A + F-08C |
| `colbert_client.py` | monolito | Método `search_by_product_id_with_category_boost()` |

Todos los cambios aditivos — ninguna línea preexistente eliminada.

### Próximos pasos

1. **Fase 1b** — extender Composite Embedding a F-08B con `alpha=0.2`, resuelve directamente el Gap C cuantificado arriba.
2. Evaluar alpha por tipo en vez de global para F-08/F-08C (COLLARES).
3. Monitorear startup/Redis en el próximo deploy.
4. Backlog sin relación, ya documentado: gap ZAPATOS/CONJUNTOS en `_B08_SHOPIFY_TO_OUTFIT_CAT`, Problema 3 (asyncpg idle connections), Artifact Registry lifecycle policy, Secret Manager audit.

DCT local equivalente: `DCT_Composite_Embedding_Fase1_a_3b_Cierre_23072026.md` (raíz del repo).