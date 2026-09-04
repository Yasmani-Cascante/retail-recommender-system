
# DCT — Fase 1b: Composite Embedding para F-08B (Cierre)

**Fecha de cierre:** 24/07/2026
**Precedido por:** DCT_Composite_Embedding_Fase1_a_3b_Cierre_23072026.md (raíz del repo)
**Documento de plan:** PLAN_Fase1b_Revision_Arquitectonica_23072026.md (mismo directorio) — mantener como referencia histórica del diseño, este DCT resume el resultado final.
**Revisiones desplegadas:** embedding-service (Fase 1b, 23/07) + `retail-recommender-00269-szm` (monolito, 23/07)

---

## 1. Resumen ejecutivo

Fase 1b extiende Composite Embedding Granular a F-08B ("qué accesorios combinan con este"), resolviendo el gap cuantificado al cerrar Fase 1→3b: cuando el pool visual genérico de un bucket está dominado por el propio tipo del ancla, la variedad se agota antes de llegar al usuario (caso extremo: 1 solo producto).

Antes de implementar, se hizo una revisión arquitectónica estratégica (rol Staff/Principal Architect + CTO) pensando en una plataforma SaaS multi-tenant futura. Esa revisión cambió el diseño original (un cuarto diccionario de taxonomía hardcodeado) por una arquitectura más limpia, ejecutada en 4 pasos. **Validado en producción con confirmación directa en el widget: buena variedad real de tipos.**

---

## 2. Decisiones arquitectónicas clave

1. **Taxonomía consolidada en un solo módulo** (`src/recommenders/product_taxonomy.py`) — reemplaza 3 estructuras dispersas (`SHOPIFY_TYPE_TEXT_PROMPTS`, `_B08_SHOPYFY_TO_OUTFIT_CAT`, uso relevante de `CATEGORY_KEYWORDS`). Alpha por tipo desde el diseño (`alpha_reinforce`, `alpha_complement`), no global — resuelve de raíz el hallazgo de que COLLARES necesita más refuerzo que CARTERAS, sin otro refactor futuro.

2. **Contrato del embedding-service simplificado (Opción B)**: en vez de que el monolito mande una clave de categoría (`boost_category=COLLARES`) que el embedding-service resuelve internamente, el monolito manda el texto ya resuelto (`boost_text=...`). El embedding-service deja de necesitar CUALQUIER conocimiento de taxonomía de tenant — se vuelve una capacidad genérica ("combina esta imagen con este texto y busca"). Hecho de forma aditiva (endpoint/método nuevos en paralelo a los de Fase 3b) para no romper la ventana de deploy.

3. **Búsqueda FAISS batcheada**: en vez de N llamadas HTTP + N búsquedas FAISS separadas (una por tipo hermano), una función nueva resuelve N textos (batch encode de los que falten) y hace **una sola** llamada a `faiss_index.search()` con una matriz de N vectores compuestos. Mejora la latencia y evita que el costo escale linealmente con la riqueza de la taxonomía.

4. **Integración en F-08B 100% aditiva**: los candidatos dirigidos por tipo se agregan a `_b08_outfit_cats[bucket]` justo después de construirlo — toda la lógica downstream ya validada (mismo-tipo, interleave por subtipo, pools fresh/full, fix de loop infinito de 16/07) opera sin cambios sobre la lista combinada.

**Explícitamente diferido** (documentado en el plan, no construido ahora): config de taxonomía respaldada por base de datos por tenant, derivación automática del "ancla semántica" por tipo desde centroides del propio catálogo (en vez de prompts escritos a mano), clasificación asistida por LLM al onboardear un tenant nuevo. Quedan como iniciativa arquitectónica separada para cuando un segundo tenant esté cerca del horizonte.

---

## 3. Validación final (23-24/07/2026)

6 consultas de prueba, revisión `retail-recommender-00269-szm`:

| Query | Ancla (tipo) | Resultado |
|---|---|---|
| Similitud (F-08 Fase A) | AROS | `boost activo (type=AROS, alpha=0.5)` — sin regresión |
| Similitud (F-08C) | VESTIDOS LARGOS | Correctamente **sin** boost (tipo sin `steering_text`) — plain search, sin error |
| Combinar (F-08B) | VESTIDOS LARGOS | `9 tipos con boost dirigido` — ancla fuera de ACCESSORIES, ningún tipo excluido, generaliza bien |
| Similitud (F-08C) | COLLARES | `boost activo (type=COLLARES, alpha=0.5)` |
| Combinar (F-08B) | COLLARES | `8 tipos con boost dirigido`, 8 productos frescos |
| Combinar (F-08B) | CARTERAS | `8 tipos con boost dirigido`, 8 productos frescos, categorías completas (dress/top/bottom/accessory/bag/enterito/outerwear/shoes) |

Cero errores, cero `AttributeError`, cero fallback roto. **Confirmado por Yasmani en el widget: buena variedad real de tipos** en las 3 consultas de "combinar" (no solo en el pool crudo de los logs).

Ruido conocido, sin relación: LFM sigue caído (404, externo, desde 10/07 — ya documentado); blip menor de Redis (1.1s, autorrecuperado, mucho más leve que el de la sesión anterior).

---

## 4. Hallazgo abierto (no bloqueante)

En las 3 consultas de "combinar", el bucket `bag` resultó siempre 100% `CARTERAS` — la llamada dirigida a `CLUTCH` tuvo éxito (batch completo, sin fallos) pero sus resultados nunca aparecieron etiquetados como `CLUTCH` en el desglose. **RESUELTO (24/07/2026, verificado en Shopify Admin por Yasmani):** de ~57 productos con "Clutch" en el título, solo UNO tiene `product_type` real igual a `CLUTCH` (`CLUTCH LEONOR PLATEADO`), y esta **Archived, 0 en stock**. Todos los demas (Clutch Lorenza, Victoria, Lorena, Antonieta, Indio...) están tipificados como `CARTERAS`. `CLUTCH` es un valor de tipo vestigial en el catalogo -- no es un bug del mecanismo, simplemente no hay inventario activo real de ese tipo para encontrar. No requiere accion.

---

## 5. Archivos modificados (estado final)

| Archivo | Servicio | Cambio |
|---|---|---|
| `src/recommenders/product_taxonomy.py` | monolito | **Nuevo** — única fuente de verdad de taxonomía |
| `src/api/services/embedding-service/visual_retriever.py` | embedding-service | +`search_by_product_id_with_text_boost`, +`search_by_product_id_with_multi_text_boost`, +`_text_boost_cache` lazy |
| `src/api/services/embedding-service/main.py` | embedding-service | +endpoint `GET /v1/embed/search-by-id-with-text-boost`, +endpoint `POST /v1/embed/search-by-id-with-multi-text-boost` |
| `src/api/services/colbert_client.py` | monolito | +métodos cliente correspondientes |
| `src/api/core/mcp_conversation_handler.py` | monolito | F-08 Fase A + F-08C migrados a `product_taxonomy`; F-08B: nuevo bloque aditivo de boost dirigido por tipo |

Funciones/endpoints de Fase 3b (`*_category_boost`) siguen presentes sin uso — limpieza pendiente para una sesión futura, no urgente.

---

## 6. Aprendizajes clave

1. **Una revisión arquitectónica antes de implementar cambió sustancialmente el diseño para mejor** — el diseño táctico original (un cuarto diccionario disperso) habría funcionado para el caso actual, pero habría profundizado la deuda de acoplamiento a un solo tenant. Vale la pena este tipo de pausa estratégica antes de features que tocan el corazón de la lógica de recomendación, no solo para bugs.
2. **Cambiar un contrato ya desplegado (Fase 3b) es seguro si se hace de forma aditiva** — mismo patrón que ya funcionó para el incidente de Fase 3: nueva ruta en paralelo, migrar consumidores, limpiar después. Cero ventana de riesgo, cero necesidad de coordinar el orden de despliegue entre los dos servicios.
3. **Los logs no siempre alcanzan para validar el resultado final que ve el usuario** — el pool crudo mejoró medible y verificablemente en los logs, pero confirmar que la mejora llegó al usuario final requirió preguntar directamente, no asumir a partir de los datos crudos.

---

## 7. Proximos pasos (consolidado, actualizado 26/07/2026 -- ver tambien secciones 8, 9, 10 y 11)

**Backlog activo de esta linea de trabajo:**
1. **Prioridad revisada al alza (26/07/2026, ver seccion 11.3)**: script de auditoria por centroides FAISS (embedding de imagen de cada producto vs. centroide de su propio `product_type` declarado). Ya no es solo "idea de backlog, no urgente" -- ahora resuelve tres cosas a la vez: (a) deteccion sistematica de mistagging tipo CARTERAS/vestido, (b) confirmar o descartar la duda pendiente del "Tocado Peineta Amaia" (`product_type=AROS`, sin confirmar), y (c) una auditoria de cobertura de `product_taxonomy.py` mas confiable y barata que el metodo manual usado hoy (enumera tipos reales desde el indice FAISS en vez de adivinar nombres de variantes).
2. Busqueda dirigida por atributos (color) -- documentado en detalle en `BACKLOG_Busqueda_por_Atributos_Color_24072026.md` (mismo directorio).
3. Iniciativa arquitectonica separada (no urgente, ver seccion 3 del PLAN): config de taxonomia por tenant en base de datos + derivacion automatica por centroide de catalogo.

**Backlog sin relacion con Composite Embedding, de sesiones anteriores:**
4. Artifact Registry lifecycle policy, Secret Manager audit.

~~Confirmar si el fix del addendum (NOVIAS LARGOS + _b08_belongs_to_bucket) ya se desplego~~ -- **RESUELTO (26/07/2026): desplegado y confirmado, ver seccion 9.**
~~Confirmar en Shopify Admin si CLUTCH tiene inventario real suficiente~~ -- **RESUELTO, ver seccion 4.**
~~Gap ZAPATOS/CONJUNTOS en el mapeo de outfit-slot~~ -- **VERIFICADO RESUELTO (24/07/2026): `product_taxonomy.py` ya incluye `ZAPATOS` y `CONJUNTOS FALDAS/PANTALONES` desde el port inicial.**
~~Caso 3, diseno pendiente~~ -- **RESUELTO (26/07/2026): disenado y aplicado, ver seccion 10. Pendiente desplegar y validar.**
~~Observabilidad: F-08 Fase A sin desglose por tipo~~ -- **RESUELTO (26/07/2026): ver seccion 11.1. Pendiente desplegar.**
~~Limpieza de `*_category_boost`~~ -- **RESUELTO (26/07/2026): ver seccion 11.2. Pendiente desplegar.**
~~Auditoria completa de cobertura de `product_taxonomy.py`~~ -- **COMPLETADA con alcance dirigido (26/07/2026): ver seccion 11.3. `NOVIAS CORTOS`/`NOVIAS MIDIS` agregados. Metodo actual no es exhaustivo -- ver punto 1 arriba para el metodo recomendado a futuro.**

---

## 8. Addendum — Fix post-cierre (24/07/2026)

En pruebas adicionales tras el cierre, se encontró un vestido (`NOVIAS LARGOS`) entre los resultados de "qué accesorios combinan con este AROS" — confirmado en logs: `F-08B candidate breakdown: bucket='accessory' {..., 'NOVIAS LARGOS': 1}`. **No originado por Fase 1b** (no está entre los 8 tipos pedidos dirigidamente) — vino del pool genérico preexistente (`search_outfit_by_image()`), el mismo tipo de sangrado entre buckets ya observado con `CAPAS BORDADAS` en la validación anterior, pero esta vez sobrevivió hasta el resultado final.

Causa raíz de dos partes:
1. **Gap de cobertura**: `NOVIAS LARGOS`/`NOVIAS ENTERITOS` nunca estuvieron mapeados a ningún outfit-slot — ni en el diccionario original (`_B08_SHOPIFY_TO_OUTFIT_CAT`) ni en `product_taxonomy.py` (portado 1:1, fiel al original).
2. **Gap estructural**: `_b08_is_same_type()` solo compara contra el tipo del ANCLA, nunca verificó si un candidato realmente pertenece al bucket donde fue colocado.

**Fix aplicado** (mismo día, sin necesidad de reabrir Fase 1b):
- `product_taxonomy.py`: agregados `NOVIAS LARGOS` → `dress`, `NOVIAS ENTERITOS` → `enterito` (solo con evidencia directa de logs — no se adivinaron variantes CORTOS/MIDIS sin evidencia).
- `mcp_conversation_handler.py`: nueva función `_b08_belongs_to_bucket()`, complemento de `_b08_is_same_type()` — usa `product_taxonomy.get_outfit_slot()` para verificar que el tipo real del candidato pertenece al bucket declarado; fail-open si el tipo no está catalogado (evita perder variedad legítima por cobertura incompleta). Integrado como tercera condición en `_b08_pools_full`.

Validado: sintaxis OK, diff 100% aditivo, T8/hermanas/is_same_type/interleave_by_subtype intactos. **Pendiente de desplegar y confirmar con logs reales.**

Relevante para el backlog (punto 3 arriba): dado que este fix estructural (`_b08_belongs_to_bucket`) ahora existe, cualquier gap de cobertura similar en la taxonomia (ej. ZAPATOS/CONJUNTOS si aplica) se manifestara como productos silenciosamente descartados en vez de colarse al usuario -- mas seguro, pero vale la pena una auditoria completa de cobertura de `product_taxonomy.py` contra el catalogo real de Shopify en algun momento.

---

## 9. Addendum 2 -- Casos 1/2/3, calibracion de alpha, deploy y validacion (25-26/07/2026)

Sesion posterior de pruebas adicionales ("muchas consultas"), seguida de una calibracion de alpha con evidencia real, un deploy, y una validacion completa. Se cierra con el sistema en un estado limpio, sin regresiones y con el fix del addendum 1 confirmado desplegado.

### 9.1 -- Caso 1: vestido en resultados de "accesorios" (RESUELTO -- dato de catalogo, no codigo)

Ancla "VESTIDO LARGO DE FIESTA SARA GASA BURDEO", query "que accesorios combinan con este vestido" -- aparecio "vestido-largo-de-fiesta-lea-turquesa-claro" entre los resultados. Patron llamativo: siempre el MISMO SKU exacto, sin importar el ancla.

**Causa confirmada por Yasmani en Shopify Admin**: ese producto tenia `product_type = "CARTERAS"` -- un vestido literalmente mal tipificado como cartera en el dato fuente. Esto explica todo: `_b08_belongs_to_bucket()` (addendum 1) pregunta si el tipo del candidato mapea al bucket declarado -- `CARTERAS` -> `bag` es una coincidencia VALIDA segun el dato del catalogo, asi que el filtro no lo detecta (no es su trabajo detectar errores de tipeo humano, solo sangrado entre buckets). Explica tambien el "siempre el mismo SKU": no es un patron sistemico, es un solo dato incorrecto.

**Resuelto por Yasmani directamente en Shopify** (cambio de `product_type` a `VESTIDOS LARGOS` + recategorizacion de colecciones) -- ningun cambio de codigo necesario. Idea de backlog anotada: un script de auditoria que compare el embedding de imagen de cada producto contra el centroide de su propio `product_type` declarado podria detectar este tipo de error de tipeo automaticamente (reutiliza infraestructura ya existente) -- no construido, solo anotado.

### 9.2 -- Caso 2: intent "este" vs "esto" (RESUELTO, confirmado en produccion)

**Causa raiz** (`src/api/core/intent_detection.py`, lineas 458 y 508): el regex que detecta "combinar"/"complementar" como outfit-completion requiere que el verbo vaya seguido de `con`, `esto`, o `esta` -- **"este" no estaba en la lista**. Confirmado letra por letra contra 3 consultas reales de los logs: "combinar esto" matcheaba, "combinar este" no matcheaba en ninguna de las 2 alternativas del regex (la alternativa B solo cubre formas conjugadas terminadas en vocal+n/s opcional, no el infinitivo "combinar").

**Fix aplicado**: agregado `este` a ambas listas (`intent_detection.py`, 2 lineas). Validado localmente corriendo el regex real contra las 5 consultas de los logs antes de aplicar (incluyendo casos de control que no debian romperse).

**Confirmado en produccion (26/07/2026, revision `00271-wn8`)**: consulta real "Con que accesorios puedo combinar este?" ahora clasifica `TRANSACTIONAL` con el log `Rule-based TRANSACTIONAL protected from ML override (ML said INFORMATIONAL @ 0.95)` -- activa F-08B correctamente (`8 tipos con boost dirigido`, `8 productos`). Antes del fix, esta misma consulta fallaba exactamente asi.

### 9.3 -- Caso 3: Brazalete->Aros, LLM no explica (DIAGNOSTICADO, fix pendiente -- ver seccion 10)

Ancla "Brazalete Esclava Lucila", query de similitud -- devolvio mayoritariamente AROS, y el LLM describio el resultado con lenguaje de "complementa perfectamente" sin aclarar que el ancla pedido (BRAZALETES) escaseaba en el pool.

**Causa raiz confirmada en codigo** (`mcp_conversation_handler.py` ~linea 2107 vs ~linea 2174, y `mcp_personalization_engine.py` ~linea 3150-3260): existe un mecanismo `category_exhausted_info` que le avisa al LLM "no digas complementa" -- pero SOLO se activa en la rama `elif len(_c08_candidates) > 0:` (pool insuficiente en cantidad total). Cuando el pool tiene SUFICIENTES candidatos pero mal distribuidos por tipo (la rama `if len(_c08_candidates) >= n_recommendations:`, que fue la que corrio), el aviso nunca se dispara -- no hay senal para este escenario especifico, aunque el resultado final sea de baja pureza de tipo.

No fue corregido en esta sesion -- se opto por calibrar alpha primero (ver 9.4). Diseno pendiente para la proxima sesion, ver seccion 10.

### 9.4 -- Calibracion de alpha para COLLARES/BRAZALETES/BRAZALETE (alpha_reinforce: 0.5 -> 0.3)

**Correccion propia importante**: el comentario original en `product_taxonomy.py` sugeria "alpha_reinforce mas alto" para COLLARES -- error de razonamiento, corregido antes de aplicar nada. Evidencia real de un experimento analogo (proyecto S1 Outfit Search, 14/05/2026, misma tecnica de composite embedding): "a menor alpha, mas influencia del texto de categoria -> mayor diversidad" -- confirma que MENOS peso de imagen (alpha mas bajo) es la direccion correcta cuando la imagen domina hacia el tipo equivocado, no mas.

**Metodologia**: se extendio `fase0_poc.py` (docs/0_plans/.../Composite_Embedding_Granular/) con dos mediciones nuevas:
- `compute_visual_similarity_scores()`: similitud coseno imagen-imagen pura (sin texto) del top-10 contra el ancla -- responde "¿bajar alpha compromete similitud visual real?"
- `compute_anchor_type_affinities()`: similitud coseno entre la imagen PURA del ancla y cada uno de los 9 prompts de tipo -- responde "¿la foto del ancla ya esta conceptualmente mas cerca de otro tipo, antes de buscar nada?"

**Resultados (4 anclas reales, alphas 0.5/0.4/0.3):**

| Ancla | Tipo | Plana | a=0.5 | a=0.4 | a=0.3 | Afinidad conceptual propia |
|---|---|---|---|---|---|---|
| Brazalete Lucila | BRAZALETES | 6/10 | 9/10 | 10/10 | 10/10 | Gana su tipo (1er lugar) |
| Brazalete Amparo Plateado | BRAZALETES | 0/10 | 3/10 | 5/10 | 7/10 | **No gana -- AROS 1er lugar** |
| Choker Alana Triple | COLLARES | 5/10 | 8/10 | 8/10 | 8/10 | Gana su tipo (1er lugar) |
| Collar Moneda Colgante | COLLARES | 2/10 | 8/10 | 8/10 | 9/10 | Gana su tipo (1er lugar) |

Hallazgo importante: solo 1 de 4 anclas (Amparo Plateado) tiene un atractor conceptual real hacia AROS -- para los otros 3, la contaminacion en busqueda plana viene de fotos especificas del catalogo quedando visualmente cerca (estilo de fotografia similar), no de una confusion de la propia foto del ancla. El costo de similitud visual pura al bajar a alpha=0.3 fue pequeno en todos los casos (-0.007 a -0.055 segun el ancla), y mayor precisamente en el caso con atractor real (Amparo Plateado) -- consistente con que ahi la correccion exige alejarse mas de la vecindad visual natural del ancla.

**Decision**: `alpha_reinforce = 0.3` para `COLLARES`, `BRAZALETES`, `BRAZALETE` en `product_taxonomy.py` (bajado de 0.5). El resto de tipos (AROS, CARTERAS, CLUTCH, CINTURONES, TOCADOS, ALAS DE NOVIA) sin cambios en 0.5 -- ya funcionaban bien.

### 9.5 -- Deploy y validacion final (revision `retail-recommender-00271-wn8`, 26/07/2026)

7 consultas de prueba, cero errores, cero regresiones. Confirmado con evidencia directa de logs + codigo:

- `alpha=0.3` activo en produccion para los 3 tipos ajustados, tanto en F-08 Fase A como F-08C.
- Caso 2 confirmado funcionando (ver 9.2).
- **El mecanismo T8 (particion estable por tipo, existente desde el 06/07) sigue protegiendo la pureza de tipo del resultado final** incluso cuando el pool crudo aparenta estar dominado por AROS. Verificado de forma concreta: para un ancla con desglose crudo de solo 10/37 COLLARES (AROS con 24), se cruzaron los 8 IDs finales realmente entregados contra titulos ya conocidos del POC -- los 8 resultaron ser COLLARES genuinos. La particion T8 toma los candidatos del tipo exacto primero; con 10 disponibles y 8 necesarios, nunca llega a tocar los AROS del pool.
- **Explicacion de la observacion de Yasmani ("similitud un poquito dudosa" en accesorios vs. vestidos)**: no es un bug. Los vestidos no tienen `steering_text` en `product_taxonomy.py` -- su busqueda es 100% imagen pura, sin ningun costo de correccion de tipo. COLLARES/BRAZALETES ahora corren con `alpha=0.3` (70% peso de texto), un costo pequeno pero real y ya medido (seccion 9.4) que se paga deliberadamente para corregir el problema de tipo que motivo todo Fase 1/1b. La observacion cualitativa de Yasmani coincide exactamente con el numero que ya se habia medido.

Ruido conocido sin relacion: LFM sigue caido (404, externo, desde 10/07); blips de Redis (7.4s y 9.5s, autorrecuperados, mas severos que la vez anterior pero sin efecto en las pruebas). Gap de observabilidad menor: F-08 Fase A no registra desglose por tipo del pool crudo como F-08C (ver seccion 7, punto 6).

### 9.6 -- Archivos modificados en este addendum

| Archivo | Cambio |
|---|---|
| `src/api/core/intent_detection.py` | Fix Caso 2: `este` agregado a 2 patrones regex |
| `src/recommenders/product_taxonomy.py` | `alpha_reinforce` 0.5->0.3 para COLLARES/BRAZALETES/BRAZALETE, con comentarios de evidencia |
| `docs/0_plans/.../Composite_Embedding_Granular/fase0_poc.py` | +`compute_visual_similarity_scores()`, +`compute_anchor_type_affinities()`, wiring en `main()` |
| `docs/0_plans/.../Composite_Embedding_Granular/BACKLOG_Busqueda_por_Atributos_Color_24072026.md` | Nuevo -- idea de busqueda por color documentada, no implementada |

Caso 3 diagnosticado pero SIN cambios de codigo en este addendum -- ver seccion 10 para el diseno.

---

## 10. Fix de Caso 3 -- disenado y aplicado (26/07/2026)

**Fix**: dentro del camino feliz de F-08C (`if len(_c08_candidates) >= n_recommendations:`), se agrega una deteccion que cuenta cuantos de los primeros `n_recommendations` candidatos (ya particionados por T8, tipo propio primero) son genuinamente del tipo del ancla. Si son menos que `n_recommendations` -- es decir, si el corte final va a mezclar tipos hermanos aunque el pool total alcanzara -- se setea `mcp_context.category_exhausted_info` con el mismo formato exacto que ya usa la rama de relleno parcial (`category`, `shown_count`, `total_count`), reutilizando integramente el consumidor ya existente en `mcp_personalization_engine.py` que le pide al LLM no decir "complementa perfectamente" cuando el tipo pedido escasea.

Alcance: solo cuando `_c08_anchor_type_for_ranking` esta seteado -- misma condicion que gobierna la particion T8 en si (si el usuario pidio una categoria explicita por texto, este marco de "tipo propio" no aplica).

Diff 100% aditivo -- cero lineas removidas de la logica existente. Validado: sintaxis OK, T8/is_same_type/belongs_to_bucket/interleave_by_subtype intactos, identico byte a byte a la version validada localmente antes de aplicar.

**Pendiente**: desplegar y confirmar con logs reales que el aviso se dispara para el caso Brazalete Lucila (u otro ancla con el mismo patron) y que el LLM deja de decir "complementa perfectamente" cuando corresponda.

**Archivo modificado**: `src/api/core/mcp_conversation_handler.py` (unico cambio de este apartado).

---

## 11. Addendum 3 -- Observabilidad F-08 Fase A, limpieza de codigo muerto, auditoria de cobertura (26/07/2026)

Tres tareas de mantenimiento hechas en paralelo mientras se esperaba el deploy del fix de Caso 3.

### 11.1 -- Gap de observabilidad de F-08 Fase A (RESUELTO)

F-08 Fase A comparte la misma estructura de filtrado y particion T8 que F-08C, pero nunca tuvo el log `candidate breakdown` (por tipo real del pool crudo) que F-08C si tiene desde el 13/07/2026. Sin esto, auditar un turno de Fase A (Turn 1) requeria inferir la composicion cruzando IDs finales contra otras fuentes -- exactamente lo que hubo que hacer a mano durante la validacion del 26/07 (seccion 9.5).

**Fix**: agregado `F-08 candidate breakdown: {...} (anchor_type=..., total=...)`, mismo formato exacto que F-08C, insertado justo despues de construir `_f08_same_cat` y antes de la particion T8 -- puramente aditivo, no cambia ningun comportamiento, solo visibilidad.

**Archivo modificado**: `src/api/core/mcp_conversation_handler.py`.

### 11.2 -- Limpieza de `*_category_boost` (RESUELTO)

Las 3 piezas de Fase 3b sin uso desde la migracion a `*_text_boost` (Fase 1b) se removieron por completo, confirmando primero con `grep` que no quedaba ninguna referencia funcional en todo el codebase:

| Archivo | Removido | Lineas |
|---|---|---|
| `visual_retriever.py` | `search_by_product_id_with_category_boost()` + `SHOPIFY_TYPE_TEXT_PROMPTS` (huerfano, ya nada lo leia) + su loop de warmup | 136 |
| `main.py` | Endpoint `GET /v1/embed/search-by-id-with-boost` | 44 |
| `colbert_client.py` | Metodo `search_by_product_id_with_category_boost()` | 51 |

Efecto colateral: el warmup del embedding-service ahora hace 9 encodes menos al arrancar (antes precacheaba 18 categorias -- 9 de `CATEGORY_TEXT_PROMPTS` + 9 de `SHOPIFY_TYPE_TEXT_PROMPTS` duplicadas -- ahora solo 9). Validacion post-deploy: confirmar en logs de arranque que dice 9, no 18.

### 11.3 -- Auditoria de cobertura de `product_taxonomy.py` (COMPLETADA, con alcance documentado)

**Metodologia usada**: consultas dirigidas contra el catalogo real via el conector de Shopify (`search_products` con filtro `product_type:"X"`), no una revision exhaustiva de los ~3000+ productos. Se probaron variantes plausibles siguiendo el patron de gaps ya encontrados (la familia NOVIAS ya habia mostrado tener 4 variantes por largo -- LARGOS/CORTOS/MIDIS/ENTERITOS -- pero solo 2 estaban mapeadas).

**Hallazgo real**: `NOVIAS CORTOS` y `NOVIAS MIDIS` existen con inventario activo real y no estaban en `product_taxonomy.py`. Agregados (ver 11.4).

**Confirmado sin gaps**: `NOVIAS FALDAS/PANTALONES/CONJUNTOS/TOPS` no existen; `CONJUNTOS TOPS/ENTERITOS/VESTIDOS/SHORTS/CORTOS` no existen -- la cobertura de `CONJUNTOS FALDAS/PANTALONES` ya estaba completa.

**Limite honesto del metodo, documentado para quien retome esto despues**: la paginacion lineal completa del catalogo (ordenado por `product_type`, recorriendo todo) resulto impracticable -- una sola categoria (`NOVIAS LARGOS`) ocupo 3 paginas completas de 50 productos sin agotarse. El metodo usado (adivinar variantes plausibles y verificarlas dirigidamente) encuentra gaps *parecidos a los ya conocidos*, pero no garantiza encontrar un tipo completamente inesperado que no seguia ningun patron ya visto. **No es una auditoria exhaustiva** -- es una verificacion dirigida de alta probabilidad.

**Metodo recomendado para la proxima auditoria (mejor que este)**: durante esta misma sesion surgieron dos observaciones sueltas que, juntas, apuntan a una solucion mejor que repetir este proceso manual:
1. Una idea de backlog ya anotada en la seccion 9.1: un script que compare el embedding de imagen de cada producto contra el centroide de su propio `product_type` declarado, para detectar candidatos a mal-etiquetados (motivada por el caso CARTERAS/vestido).
2. Una observacion suelta de esta misma auditoria: el producto "Tocado Peineta Amaia Flores y Perlas Dorado" aparecio con `product_type=AROS` -- posible mistagging similar, nunca confirmado.

**Las dos se resuelven con el mismo script**: si se construye la idea (1), automaticamente responde la duda de (2) con evidencia real en vez de una sospecha suelta. Y como efecto colateral *gratis*, ese mismo script tendria que enumerar todos los `product_type` que existen en el catalogo indexado en FAISS para poder calcular sus centroides -- lo cual es, de por si, una auditoria de cobertura completa y automatica, sin adivinar nombres de tipos ni pelear con paginacion de 3000+ productos via API. Dado que ahora sirve para tres cosas a la vez (auditoria de cobertura confiable, deteccion de mistagging, y resolver la duda pendiente del Tocado), vale la pena reconsiderar su prioridad en el backlog -- ver seccion 7, ahora listado con esta justificacion ampliada.

**Archivo modificado**: `src/recommenders/product_taxonomy.py` (agregados `NOVIAS CORTOS`, `NOVIAS MIDIS`, ambos `outfit_slot: "dress"`).

### 11.4 -- Estado final de `product_taxonomy.py`

28 tipos totales (26 + los 2 nuevos). Linea NOVIAS ahora completa: LARGOS, CORTOS, MIDIS -> `dress`; ENTERITOS -> `enterito`.

---

## 12. Addendum 4 -- F-08B vs. F-08B.2, fallo silencioso y prioridad de categoria explicita (27-28/07/2026)

Deploy de los 3 items del Addendum 3 (revision `retail-embedding-service-00052-bf7` + `retail-recommender-00273-kqb`), 8 consultas de prueba. Confirmado: 9 categorias en warmup, F-08 candidate breakdown funcionando en Fase A, 403 correcto en los 3 endpoints directos (embedding-service bien cerrado, `--no-allow-unauthenticated`). Caso 3 no se disparo en esta ronda (ninguna de las 8 consultas tuvo el patron exacto) -- pendiente de una prueba dedicada.

### 12.1 -- Hallazgo: T8 "con que vestidos combina mejor?" (ancla AROS) no devolvia vestidos

Primera aclaracion importante: el log `solucion_b_suppressed_category_mismatch` que aparecio en el mismo turno **no es la causa** -- es un mecanismo distinto (`mcp_personalization_engine.py`, "Solucion B (UX)") que decide si el LLM debe mencionar el producto que el usuario esta viendo por su nombre al responder. Cuando detecta que la consulta pide una categoria distinta a la del producto visto, suprime esa mencion -- para no decir "El Aros..." cuando el usuario pregunto por vestidos. Funciono exactamente como debia; es una coincidencia de timing, no la causa del problema.

**Causa real, confirmada linea por linea en `mcp_conversation_handler.py`**: existe un mecanismo mas antiguo, `F-08B.2` (~linea 1751), con su propio `_OUTFIT_COMPLEMENT_MAP` hardcodeado -- disenado **exclusivamente** para la direccion "ancla es una prenda -> recomendar accesorios que combinan" (ej. `VESTIDOS LARGOS -> [AROS, COLLARES, CLUTCH, TOCADOS, CINTURONES]`). El propio comentario del codigo admite que nunca se agregaron entradas para anclas de tipo accesorio. Cuando el ancla es AROS (accesorio) pidiendo vestidos (direccion inversa, nunca contemplada), el mapa no encuentra clave y cae al fallback generico `[AROS, COLLARES, CLUTCH, CINTURONES]` -- puramente accesorios, sin importar lo que el usuario pidio.

El sistema SI detecto correctamente la categoria pedida mas arriba en el mismo flujo (`F-08B query category detected: [...] -> ['dress']`), pero F-08B.2 la descartaba en silencio -- confirmado por el log `F-08B.2 query suppressed: outfit_complement_f08b2 activo`.

### 12.2 -- Por que corrio F-08B.2 en vez del F-08B principal (rastreo completo)

Se rastreo el codigo completo desde el gate de entrada (`VISUAL_SEARCH_ENABLED`, linea ~908) hasta el final del bloque F-08B principal (linea ~1560). Confirmado con certeza:

1. El bloque F-08B principal (Fase 1b, el que construimos toda la sesion anterior) **si arranco** para T8 -- la deteccion de categoria (`_b08_query_target_cats = ['dress']`) ocurre DENTRO del mismo bloque anidado gateado por `VISUAL_SEARCH_ENABLED`, confirmado por nivel de indentacion.
2. La busqueda se hizo con `target_categories=['dress']` -- un solo bucket, combinando la imagen de un AROS con el prompt generico de "dress" (los tipos vestido nunca tuvieron `steering_text` propio, fuera de alcance de Fase 1b).
3. **El bug exacto**: al final del bloque (`if _b08_recs: ... return _b08_recs`), **no existia ningun `else`** para el caso en que `_b08_recs` terminara vacio sin ningun error ni timeout. Sin excepcion que capturar, sin log que escribir, el codigo caia en silencio total hacia el siguiente mecanismo disponible (F-08B.2).

**Dos hipotesis abiertas sobre POR QUE `_b08_recs` termino vacio** (no se distinguio con certeza cual, o si ambas se combinaron): (a) la busqueda compuesta imagen-AROS + texto-generico-"dress" genuinamente encontro pocos o ningun vestido util, o (b) T8 es el turno 8 de una conversacion larga (`shown_products count: 56`) -- una busqueda de una sola categoria tiene mucho menos margen para encontrar algo fresco que la busqueda amplia de 8 categorias que usan la mayoria de los otros turnos.

### 12.3 -- Fix 1: log del caso vacio (aplicado)

Agregado un `else:` en el punto exacto donde antes no habia nada -- puramente aditivo, no cambia ningun comportamiento, solo hace visible la proxima vez que esto pase:

```python
if _b08_recs:
    ...
    return _b08_recs
else:
    logger.info(
        f"F-08B outfit_completion: 0 productos para "
        f"target_categories={_b08_target_cats}, "
        f"anchor_type={_b08_ptype!r}, pid={_b08_pid!r}, "
        f"shown_products_count={len(_b08_shown_ids)} -- "
        f"cayendo a mecanismo de fallback"
    )
```

### 12.4 -- Fix 2: prioridad de categoria explicita en F-08B.2 (aplicado)

Dentro del bloque F-08B.2, se agrega una rama: si `_b08_query_target_cats` (calculado mas arriba, accedido de forma segura via `locals().get()` para evitar `NameError` si el bloque principal nunca corrio) tiene contenido, el usuario nombro una categoria explicita -- esa peticion tiene **prioridad absoluta** sobre el mapa de complemento del ancla. Se resuelve a tipos Shopify reales via `product_taxonomy.types_in_outfit_slot()` (unica fuente de verdad ya establecida en Fase 1b) en vez de mantener un tercer mapa hardcodeado en paralelo. Sin categoria explicita, el comportamiento original (mapa `_OUTFIT_COMPLEMENT_MAP` keyed por el tipo del ancla) sigue exactamente igual, sin cambios.

Validado con simulacion funcional real (no solo sintaxis) usando `product_taxonomy.py` real:
- Caso T8 (ancla=AROS, query detecto `['dress']`): antes devolvia `['COLLARES', 'CLUTCH', 'CINTURONES']`; con el fix devuelve los 6 tipos reales de vestido (`VESTIDOS CORTOS/LARGOS/MIDIS`, `NOVIAS LARGOS/CORTOS/MIDIS`).
- Caso sin categoria explicita (comportamiento original): identico a antes, confirmado sin cambios.
- Caso limite (auto-exclusion): si el ancla es del mismo tipo que la categoria pedida, se excluye correctamente de sus propias sugerencias.

Diff 100% aditivo en ambos fixes -- cero logica preexistente removida (T8/is_same_type/belongs_to_bucket/interleave_by_subtype/Caso 3/F-08 candidate breakdown, todos verificados intactos tras aplicar). Sintaxis validada.

**Pendiente**: desplegar y confirmar con logs reales -- repetir la consulta "con que vestidos combina mejor?" sobre un ancla AROS y verificar que ahora aparecen vestidos genuinos.

### 12.5 -- Hallazgos adicionales de esta ronda, sin cambios de codigo (backlog)

- **TOCADOS** muestra el mismo patron de dominancia de AROS que COLLARES/BRAZALETES tenian antes de la calibracion de alpha (`{'TOCADOS': 24, 'AROS': 25}`, 48%, alpha=0.5 sin ajustar) -- candidato a la misma calibracion (seccion 9.4).
- `_OUTFIT_COMPLEMENT_MAP` (F-08B.2) esta incompleto incluso en su propia direccion original: `ZAPATOS` no aparece como opcion en ninguna entrada del mapa, y `CONJUNTO` no es clave -- verificado contra los 3 ejemplos que Yasmani propuso ("zapatos para este vestido" no cubierto en absoluto; "aretes para este top" y "bolso para este conjunto" cubiertos solo parcialmente).
- `_B08_SHOPIFY_TO_OUTFIT_CAT` (linea ~955) sigue existiendo como diccionario separado de `product_taxonomy.py`, usado especificamente para detectar categoria desde el texto de la consulta -- mismo riesgo de "bloques gemelos" que motivo el fix de NOVIAS CORTOS/MIDIS. No tocado esta sesion.
- Patron menor, recurrente (2/2 veces observado en dos sesiones distintas): el segundo turno de cada sesion de prueba muestra deteccion de intent anomalamente lenta (~440-450ms vs ~2-3ms normal). No investigado a fondo, no urgente.

### 12.6 -- Archivos modificados en este addendum

| Archivo | Cambio |
|---|---|
| `src/api/core/mcp_conversation_handler.py` | Fix 1: log de `_b08_recs` vacio (F-08B principal). Fix 2: prioridad de categoria explicita en F-08B.2, via `product_taxonomy.types_in_outfit_slot()` |
