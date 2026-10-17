# DCT — Cierre de Sesión: Unificación de Taxonomía, Herramienta de Auditoría de Catálogo, y Estado de la Unificación F-08

**Fecha de cierre:** 1 de octubre de 2026
**Naturaleza de este documento:** cierre de una sesión de trabajo muy larga — no repite el detalle ya documentado en otros DCTs, lo resume y apunta a ellos. Si necesitas el detalle técnico completo de cualquier pieza, sigue las referencias de la sección 5.
**Para continuar este trabajo en una sesión nueva:** usa `PROMPT_CONTINUIDAD_01102026.md` (mismo directorio) — está escrito específicamente para pegarse como primer mensaje de un chat nuevo.

---

## 1. Resumen de la sesión

Esta sesión cubrió cuatro bloques de trabajo grandes, en orden:

1. **Sincronización del catálogo TF-IDF y roadmap de hardening.**
2. **Limitador de tasa compartido para Shopify** (`ShopifyRebuildPriority`) — resolviendo la contención entre el rebuild diario del catálogo y el enriquecimiento de colecciones en segundo plano.
3. **Unificación de taxonomía (Fase 2)** — consolidar 4 fuentes de verdad paralelas de "tipo de producto → categoría de outfit" en una sola (`product_taxonomy.py`), con dos incrementos de extracción de lógica a funciones puras y probadas (F-08B.2, luego F-08B principal).
4. **Construcción de una herramienta de auditoría de catálogo por centroides visuales** (`taxonomy_centroid_audit.py`) — que terminó revelando, y permitiendo corregir, errores reales de categorización en el catálogo de producción.

El cuarto bloque motivó, a su vez, una investigación no trivial de autenticación de Google Cloud (documentada en detalle, ver sección 5) y una mejora de automatización (refresco automático del catálogo antes de cada auditoría).

Al cierre de esta sesión, surgió una pregunta que quedó parcialmente respondida: **¿está completa la unificación de la lógica de resolución de categoría entre las cuatro rutas del sistema (F-08 Fase A, F-08B, F-08C, F-08B.2)?** La respuesta, confirmada revisando el código real, es: **no — dos de cuatro.** Ver sección 4.

---

## 2. Bloques 1 y 2 — resumen breve

Estos dos bloques se completaron al inicio de esta sesión (antes del tramo más largo de trabajo sobre taxonomía). En resumen:

- **Sincronización del catálogo TF-IDF**: se diagnosticó y corrigió la causa raíz de por qué el catálogo interno de recomendaciones podía quedar desincronizado de Shopify durante semanas sin que nadie lo notara, y se estableció un proceso de regeneración confiable.
- **`ShopifyRebuildPriority`**: el rebuild diario del catálogo y el enriquecimiento de colecciones en segundo plano (`PASO 4.6 BG`) competían por el mismo cupo de la API de Shopify. Se implementó una señal de prioridad (el segundo proceso se pausa por completo mientras el primero está activo) — validada con evidencia real de producción en dos corridas independientes, con cero solape confirmado en ambas.

---

## 3. Bloque 3 y 4 — ya documentados en detalle, no se repiten aquí

Todo el trabajo de unificación de taxonomía y construcción de la herramienta de auditoría está documentado con el nivel de detalle que amerita en sus propios DCTs:

- **`DCT_Cierre_Fase2_Unificacion_Taxonomia_27092026.md`** (mismo directorio) — la decisión de unificación con evidencia real del catálogo, qué se retiró (`_B08_SHOPIFY_TO_OUTFIT_CAT`, `_B08B2_SHOPIFY_TO_OUTFIT_CAT`, `_OUTFIT_COMPLEMENT_MAP`), los dos incrementos de extracción (F-08B.2 primero, F-08B principal después, cada uno con su módulo puro y sus tests), la integración de "conjunto" en el sistema de conflictos de slot, y — en sus Addendums (secciones 7.1 a 7.8) — la saga completa de autenticación local de Google Cloud (cinco intentos, causa real en el quinto: `fetch_id_token()` no reconoce credenciales de impersonación, limitación reconocida oficialmente por `google-auth-library-python`), y el cierre del chequeo de texto automático.

- **`DCT_Cierre_Herramienta_Auditoria_Taxonomia_01102026.md`** (mismo directorio) — referencia completa de la herramienta en sí (los 18 apartados: objetivo, arquitectura, cálculo exacto de `similitud` y `z`, umbrales, limitaciones, oportunidades de mejora), más dos Addendums: el refresco automático del catálogo desde el bucket de GCS antes de cada corrida (eliminando el paso manual de `gsutil cp`), y la validación de circuito cerrado del 1 de octubre (una corrección real en Shopify, confirmada end-to-end: detectar → verificar → corregir → sincronizar → re-auditar → confirmar que la corrección se sostiene, con 53 de 53 candidatos confirmados por texto, cero pendientes).

**Estado de ambos bloques: completos**, con evidencia real de producción, no solo validación sintética.

---

## 4. El hallazgo de cierre: unificación F-08/F-08B/F-08C/F-08B.2 — estado real, confirmado en código

Al preguntarse si la unificación de taxonomía (bloque 3) también había resuelto la unificación de la *lógica de resolución de categoría* en las cuatro rutas del sistema, se investigó el código real (`mcp_conversation_handler.py`) en vez de asumir. Resultado:

| Ruta | Mecanismo de categoría | ¿Usa `product_taxonomy.get_outfit_slot()`? | ¿Lógica extraída a función pura + tests? |
|---|---|---|---|
| F-08B (completar outfit, camino principal) | Sistema de conflictos de slot + `get_outfit_slot()` | ✅ Sí | ✅ Sí (`f08b_target_categories.py`) |
| F-08B.2 (completar outfit, respaldo) | Mismo mecanismo, sin conflictos de slot | ✅ Sí | ✅ Sí (`f08b2_category_resolution.py`) |
| F-08 Fase A (similitud, Turn 1) | `get_parent_categories()` — expansión a categorías "hermanas" | ❌ No | ❌ No — lógica inline |
| F-08C (similitud, Turn 2+) | Mismo mecanismo que F-08 Fase A | ❌ No | ❌ No — lógica inline |

> ⚠️ **CORRECCIÓN (02/10/2026) — leer antes del párrafo siguiente.** El "hallazgo adicional" de abajo es **incorrecto**: se basó en una nota de código obsoleta. El relleno restringido **sí se portó** a F-08 Fase A el mismo 03/07/2026 (bloque `HALLAZGO 1 / OPCION A FIX`). Las divergencias reales entre F-08 Fase A y F-08C son otras, en ambas direcciones — ver **Addendum A** al final de este documento. La tabla de arriba sigue siendo correcta.

**Hallazgo adicional, no solo ausencia de unificación — una brecha concreta ya documentada desde julio y nunca cerrada:** un comentario en el propio código (fechado 03/07/2026, ampliado 18/06/2026) registra que un fix aplicado a F-08C (el "relleno restringido" del sprint del 17/06/2026) **nunca se portó a F-08 Fase A**, con una nota explícita del autor original: *"Evaluar el relleno restringido como fix adicional en una sesión futura"*. Esa sesión nunca llegó — hasta ahora, sin resolver.

**Conclusión honesta:** la unificación de taxonomía (bloque 3) resolvió la fuente de *datos* (qué bucket le corresponde a cada tipo) para las cuatro rutas por igual, ya que todas, directa o indirectamente, dependen de `improved_fallback_exclude_seen.py`/`product_taxonomy.py`. Pero la unificación de la *lógica de decisión* (qué categorías excluir, cómo expandir, cuándo tratar un pedido como específico) solo se completó para F-08B y F-08B.2. F-08 Fase A y F-08C siguen con su propio mecanismo, paralelo, no extraído, no testeado — y con una divergencia conocida entre ellos mismos, sin resolver.

---

## 5. Estado consolidado contra el roadmap original

Cruzando contra `Evaluacion_Integral_Sistema_16092026.md` (el documento raíz de este directorio, sección 15, "Roadmap recomendado"):

| Prioridad del roadmap original | Estado al cierre de esta sesión |
|---|---|
| Job/alerta de sincronización del catálogo TF-IDF | ✅ Resuelto (bloque 1; reforzado para el script de auditoría con el refresco automático del bloque 4) |
| Auditoría de pines de versión en `requirements.txt` | ✅ Resuelto (confirmado en `requirements.cloudrun.txt`, auditoría fechada 19/09/2026) |
| Validación pendiente de Fix 2 (prioridad F-08B.2/rate limiter) | ✅ Resuelto (bloque 2, evidencia real de producción) |
| Decisión explícita sobre unificar F-08/F-08B/F-08C/F-08B.2 | 🟡 Parcial — 2 de 4 rutas unificadas (ver sección 4) |
| Destino de `_OUTFIT_COMPLEMENT_MAP` | ✅ Resuelto — retirado por completo (bloque 3) |
| Harness de calibración de `alpha` | ⬜ Sin tocar esta sesión |
| Inventario/productos archivados en el índice | ⬜ Diferido por decisión explícita de Yasmani (sin cambios) |
| Multi-tenant (config por DB, centroides automáticos, etc.) | ⬜ Correctamente diferido — nada de esta sesión lo contradice |

---

## 6. Próximo paso recomendado

Investigar a fondo F-08 Fase A y F-08C (leer el código completo de ambos bloques, mapear exactamente qué lógica es compartida de hecho y cuál diverge) **antes** de decidir si conviene extraerlos a funciones puras como se hizo con F-08B/F-08B.2, o si el enfoque correcto es distinto dado que resuelven un problema diferente (similitud visual con expansión a categorías hermanas, no completar un outfit con conflictos de slot). Esta investigación es el punto de partida de la próxima sesión — ver `PROMPT_CONTINUIDAD_01102026.md`.

---

## Addendum A (02/10/2026) — Investigación de F-08 Fase A y F-08C: corrección de la sección 4 y mapa real de divergencias

**Método:** lectura completa de ambos bloques en `src/api/core/mcp_conversation_handler.py` (no solo los comentarios) + sonda sintética con los diccionarios reales del repo (`CATEGORY_KEYWORDS`, `PRODUCT_TAXONOMY`), extraídos vía `ast` sin ejecutar los módulos. Números de línea referidos al estado del archivo **después** de la edición de comentario del 02/10 (ver A.5).

### A.1 Corrección: el relleno restringido SÍ está portado a F-08 Fase A

La sección 4 afirmaba que el relleno restringido de F-08C (sprint 17/06/2026) "nunca se portó" a F-08 Fase A. Es falso:

- La nota que lo afirmaba (párrafo "Alcance de este fix", ~línea 2578) correspondía al **primer** fix de la sesión del 03/07/2026 (expansión a hermanas).
- Un **segundo** fix del mismo día — bloque `HALLAZGO 1 / OPCION A FIX` (~línea 2738), implementación en ~2813-2945 — portó el relleno completo: eventos sintéticos con peso extra al ancla, `user_query=None`, `strict_category=True`, `category_exhausted_info`, más un `try` propio que degrada a solo-visual.
- La nota del primer fix nunca se actualizó. El DCT del 01/10 heredó su conclusión sin contrastarla con el código de debajo.

**Lección:** un comentario que contradice al código se lee como evidencia y es más peligroso que la ausencia de comentario. El hallazgo se valida contra el código ejecutable, no contra su narración.

### A.2 Mapa real: un mismo pipeline duplicado, con divergencias en ambas direcciones

Ambos bloques implementan el mismo pipeline de 5 etapas: resolver categorías → filtrar pool FAISS → ordenar (T8) → camino feliz / relleno parcial / cero candidatos → normalizar. F-08C: ~1705-2275. F-08 Fase A: ~2458-2955.

| Etapa | F-08 Fase A (Turn 1) | F-08C (Turn 2+) | Clasificación |
|---|---|---|---|
| Trigger | `_is_visual_similarity_query` + `not use_diversification` | mismo regex, dentro de `if use_diversification` | Intencional |
| Composite boost | `get_steering_text` + `get_alpha(..., "reinforce")` | idéntico | Compartido |
| `top_k` FAISS | 30 | 50 | Divergente, sin justificación documentada |
| Fallback CDN (`search_by_image`) | sí | no | Intencional (producto no indexado) |
| Categoría desde el texto de la query | **nunca** llama a `extract_categories_from_query` | la intenta primero (~1778); solo expande a hermanas si el texto no nombra categoría | **Divergencia semántica — decisión de producto** |
| Expansión a hermanas | `next()` sobre `get_parent_categories()`, resultado en mayúsculas | mismo algoritmo, sin `.upper()` | Compartido (código copiado) |
| Partición T8 (tipo exacto primero) | siempre que haya tipo de ancla | solo si `_c08_anchor_type_for_ranking` está seteado | Coherente con la fila "texto" |
| Intercalado por subtipo (NIVEL 1) | sí (`_f08_interleave_by_subtype`, ~2716) | **no existe** | **Brecha inversa: fix de A nunca portado a C** |
| `category_exhausted_info` en camino feliz (Caso 3, 26/07) | **no existe** | sí (~2013) | **Brecha inversa: fix de C nunca portado a A** |
| Log "pool insuficiente" | no | sí | Observabilidad asimétrica |
| Fallo del relleno | `try` propio → solo-visual | sin `try` propio → `smart_fallback` genérico | Divergente |
| Fallo de la expansión | `logger.debug` (invisible en producción) | `logger.warning` | Divergente |
| `score_step` / `source` | 0.03 / `visual_search_f08` | 0.02 / `visual_diversification_f08c` | Intencional (telemetría) |

La regla de `learnings.md` (simetría entre rutas) se cumplió en una sola dirección (C → A). Dos fixes viajaron en sentido contrario y no se propagaron: NIVEL 1 (A → C) y el aviso de camino feliz (C → A).

**Distinción necesaria:** la expansión a hermanas de ~1549 (`FIX (28/05/2026 — diversificacion)`) **no** pertenece a F-08C. Alimenta `user_events` para la PRIORIDAD 2 de `smart_fallback`, corre antes de F-08C y para cualquier query de Turn 2+. Es un tercer consumidor independiente de `get_parent_categories()`.

### A.3 Hallazgos confirmados con la sonda sintética

**a) Bug compartido — la etiqueta de `category_exhausted_info` no es la del ancla.** Ambas rutas reportan `categorias_expandidas[0]`, que es el **primer hermano del grupo padre**, no el tipo que el usuario está viendo:

| Ancla | Categoría reportada al LLM (ambas rutas) |
|---|---|
| CAPAS GASA | CAPAS BORDADAS |
| COLLARES | AROS |
| BRAZALETES | AROS |
| VESTIDOS MIDIS | VESTIDOS LARGOS |

El caso con más probabilidad real de dispararse es CAPAS GASA: grupo de 2 tipos, categoría pequeña, la misma que motivó el sprint del 17/06. **Pendiente:** no se ha verificado cómo `mcp_personalization_engine.py` redacta el mensaje a partir de este campo, así que el impacto exacto en el texto al usuario está sin confirmar.

**b) Doble padre resuelto por orden de inserción del diccionario.** AROS, COLLARES, BRAZALETES y BRAZALETE pertenecen a `ACCESSORIES` y a `JOYAS` (este último añadido el 15/09/2026). Las tres rutas que usan `get_parent_categories()` toman el primer padre que contenga el tipo, y hoy es ACCESSORIES (9 tipos, incluyendo CARTERAS y CLUTCH) solo porque está definido antes en el archivo. Reordenar `CATEGORY_KEYWORDS` cambiaría el comportamiento de "similar a estos aros" (9 → 4 tipos) sin tocar F-08. Es un contrato implícito, no documentado.

**c) "Grupo hermano" ≠ `outfit_slot`: difieren en 31 de 36 tipos de `PRODUCT_TAXONOMY`.** El patrón de F-08B/F-08B.2 (`get_outfit_slot()`) **no se traslada tal cual**. Ejemplos con impacto de estilismo:

- **KIMONOS:** hoy sin hermanos; con `outfit_slot` serían CAPAS + CHAQUETAS. ¿Similares? Discutible.
- **VESTIDOS MIDIS:** con `outfit_slot` incluiría vestidos de NOVIA. Para similitud, casi seguro que no.
- **CARTERAS:** hoy sus "hermanos" son aros y collares; con `outfit_slot` serían solo CLUTCH, probablemente mejor.

`outfit_slot` responde a "¿qué hueco del outfit ocupa?". La similitud necesita responder a "¿qué se parece visualmente a esto?". Son dos taxonomías distintas. La de similitud vive hoy en `CATEGORY_KEYWORDS` (un diccionario de **detección por texto**), no en `product_taxonomy.py`. Por tanto, la afirmación de la sección 4 de que la unificación de taxonomía "resolvió la fuente de datos para las cuatro rutas" tampoco es exacta para F-08 Fase A y F-08C.

### A.4 Decisión de enfoque (acordada 02/10/2026)

Se extrae, pero **A con C** (ya son el mismo pipeline duplicado), **no hacia `get_outfit_slot()`**. Tres pasos, uno a la vez:

1. **Extracción sin cambio de comportamiento:** nuevo módulo puro `src/recommenders/f08_similarity_resolution.py`, con una configuración por ruta que codifica explícitamente cada divergencia actual. Tests de caracterización que fijan el comportamiento de hoy, divergencias y bug de etiqueta incluidos.
2. **Resolver divergencias una por una**, ya con red de tests: portar NIVEL 1 a C, portar el aviso de camino feliz a A, corregir la etiqueta de agotamiento y hacer explícito el desempate ACCESSORIES/JOYAS. La divergencia de texto en Turn 1 queda para decisión de producto de Yasmani.
3. **Más adelante:** decidir si la familia de similitud pasa a ser un campo propio en `product_taxonomy.py` (p. ej. `similarity_family`), distinto de `outfit_slot`.

### A.5 Cambios aplicados el 02/10/2026

- `mcp_conversation_handler.py`, párrafo "Alcance de este fix" (~2578): la nota obsoleta se reemplazó por una corrección fechada que apunta al bloque `HALLAZGO 1 / OPCION A FIX` y a este Addendum. **Validación:** `ast.parse` OK; el AST del archivo es **idéntico** al anterior (comparado con `ast.dump(..., include_attributes=False)`), lo que prueba que el cambio es solo de comentarios. +7 líneas.
- Este documento: aviso de corrección dentro de la sección 4 + este Addendum.

### A.6 Paso 1 — extracción sin cambio de comportamiento (02/10/2026): módulo y tests creados, handler aún NO cableado

**Archivos nuevos** (ninguno importado todavía por código de producción; cero impacto en runtime):

| Archivo | Contenido |
|---|---|
| `src/recommenders/f08_similarity_resolution.py` | Una función pura por etapa del pipeline + `SimilarityRouteConfig` con dos instancias (`F08A_ROUTE`, `F08C_ROUTE`) que codifican **todas** las divergencias de la tabla A.2 como campos explícitos. Dependencias inyectadas (`get_parent_categories_fn`, `type_of`), mismo criterio que `f08b2_category_resolution.py`. Comentarios ASCII. |
| `tests/unit/test_f08_similarity_resolution.py` | 52 tests de caracterización. Fijan el comportamiento **actual**, incluido el bug de etiqueta (`test_bug_conocido_etiqueta_es_primer_hermano`) y cada divergencia; los marcados "PASO 2" son los que deben cambiar, a propósito, al corregirlas. |
| `tests/characterization/equiv_harness_f08.py` | Oráculo: `ref_f08a()` / `ref_f08c()` son copias **literales** de la lógica inline del handler, comparadas contra el módulo. No es un test de pytest. Tras cablear el handler será la única copia de la lógica original: **no borrar hasta cerrar el paso 2**. |

**Validación:**

- `ast.parse` OK en los tres archivos; los tres verificados byte a byte (SHA-256) entre el sandbox de validación y el repo.
- `pytest tests/unit/test_f08_similarity_resolution.py`: **52 passed**.
- Arnés de equivalencia: **40.000 casos (20.000 A + 20.000 C), 0 divergencias**, con los diccionarios reales del repo. Cobertura de caminos: A feliz/parcial/vacío = 4.599 / 8.111 / 7.290; C = 4.287 / 9.203 / 6.510. Incluye casos adversariales: ancla vacía o desconocida o en minúsculas, IDs fuera del índice, productos sin `product_type`, el propio ancla dentro del pool, `get_parent_categories` que lanza excepción y orden del mapa barajado.
- **Mutation testing del arnés:** 6 de 6 mutantes detectados (C con NIVEL 1, A con aviso de camino feliz, A sin intercalado, tag de relleno cambiado, etiqueta de agotamiento corregida, desempate doble padre → JOYAS). Cuatro de ellos son exactamente los cambios previstos para el paso 2: cada uno romperá el arnés y su test de forma visible.

**Única normalización deliberada:** la exclusión del ancla compara `str(pid) != str(anchor_pid)` en ambas rutas. F-08C usaba `pid != anchor_pid`. Es equivalente bajo el contrato de `colbert_client`, cuyos tres métodos de búsqueda están anotados `-> Optional[List[str]]` y devuelven `data['product_ids']` (verificado en el código).

**Pendiente (requiere "aplícalo" explícito):** cablear `mcp_conversation_handler.py` para que ambos bloques llamen al módulo en lugar de su lógica inline. Esto **sí** toca producción: va en un commit aparte, verificado contra el oráculo, con deploy y validación con logs reales de Cloud Run antes de iniciar el paso 2.

### A.7 Paso 1b — cableado de F-08C al módulo (02/10/2026): APLICADO en el repo, pendiente de deploy

Con "aplícalo" de Yasmani. F-08 Fase A **todavía no** se ha cableado: va en un cambio separado, después de validar este en producción (un cambio a la vez).

**Qué cambió en `mcp_conversation_handler.py`:** el cuerpo de `if _c08_visual_ids and _c08_tfidf and hasattr(...)` (antes ~1770-2261, ahora ~1770-2025) llama a `f08_similarity_resolution` con `F08C_ROUTE`. El archivo pasa de 3687 a 3453 líneas (−234). Se mantienen en el llamador: la extracción de categorías por texto (depende de `all_products`), la llamada a `smart_fallback`, `normalize_recommendation_dict` y **todos los logs, con formato idéntico** (las consultas de Cloud Logging existentes siguen sirviendo). El import es lazy, mismo patrón que BUG-REFACTOR-1. El historial de fixes que vivía en comentarios del bloque se conserva en los docstrings del módulo y en este Addendum.

**Ajuste previo al módulo:** `CategoryResolution.expansion_error` pasa de `repr(exc)` a `str(exc)`, porque el warning original interpolaba la excepción con `str()`. Revalidado: 52/52 tests, 40.000 casos sin divergencias.

**Validación del cableado (sobre el código real, no sobre el módulo):**

- **Prueba diferencial:** el bloque inline anterior y el bloque nuevo, ambos extraídos literalmente del handler, se ejecutaron con `exec` en un entorno simulado idéntico. **6.000 casos idénticos** en valor de retorno, **cada línea de log** (nivel + texto), argumentos de cada llamada a `smart_fallback` y `category_exhausted_info`. Cobertura: 2.109 sin retorno (cae a `smart_fallback`), 871 camino feliz, 437 feliz con aviso, 1.153 parcial con agotamiento, 1.430 parcial con relleno. Repetida tras aplicar, extrayendo el bloque nuevo **del archivo real del repo**.
- **Mutation testing de la prueba diferencial:** 5/5 detectados (un espacio extra en un log, `strict_category=False`, `user_query` no suprimido, warning→info, `score_step` 0.02→0.03).
- `ast.parse` del handler completo OK. Fuera del bloque, el archivo es idéntico línea a línea al anterior (1.769 líneas de prefijo y 1.427 de sufijo).

**Riesgo residual y qué vigilar tras el deploy:** cualquier excepción del código nuevo (p. ej. `ImportError` si el módulo no llegara a la imagen Docker) la captura el `except Exception` del bloque y **degrada en silencio** a `smart_fallback`, emitiendo solo `F-08C visual fallback: <error>`. Ese warning es la señal de regresión número uno. La señal de éxito es ver los logs habituales (`F-08C category expansion`, `F-08C candidate breakdown`, `F-08C visual_diversification` / `visual_partial_plus_fill`) en turnos 2+ de similitud.

---

## Addendum A.8 — Validación en producción del cableado F-08C (02/10/2026)

**Corrida:** revisión `retail-recommender-00308-jhb`, 12:22:52–12:32:02 UTC, 2.161 entradas de log, sesión única `widget_session_1790863413242_ly2yg7uj2`. 9 turnos; 7 pasaron por F-08C.

### A.8.1 Veredicto

**Cableado validado. Cero regresiones.** Ninguna señal de regresión presente: 0 `F-08C visual fallback`, 0 `visual timeout`, 0 `ImportError`, 0 `Traceback`, 0 ERROR/CRITICAL. En los 8 `candidate breakdown` emitidos, la suma de valores coincide con `total=`.

### A.8.2 Turnos ejecutados

| # | Consulta | Ancla | Ruta | Resultado |
|---|---|---|---|---|
| T1 | Muéstrame productos similares | AROS | F-08 Fase A | `visual_similarity: 8` — Fase A intacta |
| T2 | Muéstrame productos similares | BRAZALETES | F-08C `parent_group` | breakdown 30/12/1/5/1/1=50, feliz, sin aviso |
| T3 | Muéstrame accesorios similares | COLLARES | F-08C `query_text` | `anchor_type='COLLARES'` — **fix 18/07 OK** |
| T4 | Recomiéndame productos similares a este | COLLARES | F-08C `parent_group` | AROS 31 / COLLARES 10 = 41, feliz |
| T5 | Muéstrame bolsos similares a este | COLLARES | F-08C `query_text` sin ranking | 0 candidatos → `POOL_EMPTY` |
| T6 | Muéstrame bolsos similares a este | COLLARES | F-08C `query_text` sin ranking | 0 candidatos → `POOL_EMPTY` |
| T7 | Muéstrame productos similares | KIMONOS | F-08C `exact_type` | `cats=['KIMONOS']`, 26 candidatos, feliz |
| T8 | muestrame kimonos | KIMONOS | **ninguna** | control negativo: 0 líneas F-08C |
| T9 | Muéstrame vestidos similares | VESTIDOS CORTOS | F-08C `query_text` | 3 tipos de vestido, sin NOVIAS |

Las **cuatro** vías de `resolve_similarity_categories` quedaron ejercitadas: `parent_group` (T2, T4), `query_text` con ranking (T3, T9), `query_text` sin ranking (T5, T6) y `exact_type` (T7).

### A.8.3 Cobertura pendiente (bloquea el cierre del paso 1b)

De los tres caminos de `classify_pool`, **solo dos** se ejercitaron en producción:

| Camino | Estado |
|---|---|
| `POOL_HAPPY` sin aviso | Ejercitado (T2, T3, T4, T7, T9) |
| `POOL_EMPTY` | Ejercitado (T5, T6) |
| `POOL_HAPPY` **con** aviso (`detect_happy_path_shortfall`) | **Sin ejercitar** |
| `POOL_PARTIAL` (`build_partial_fill_events`, `visual_partial_plus_fill`) | **Sin ejercitar** |

El Caso 5 (CAPAS GASA), omitido en esta corrida, es el que cubre ambas. Las dos ramas están verificadas por la prueba diferencial de 6.000 casos (A.7), pero **no** con tráfico real.

### A.8.4 Hallazgo positivo: la calibración de Fase 1b está funcionando

T2 (ancla BRAZALETES) **no** disparó el aviso de camino feliz, contra lo previsto a partir del incidente del 26/07/2026. El motivo es bueno: con `alpha=0.3` del composite embedding, el breakdown da **30 BRAZALETES de 50** en el pool. El ancla ya no queda desplazada por AROS, que era exactamente el síntoma de julio.

### A.8.5 Caso 4 — análisis de la anomalía reportada

**Síntoma:** "Muéstrame bolsos similares a este" sobre un COLLARES devolvió 1 cartera correcta en T5, y en T6 (mismo tipo de ancla, producto distinto) devolvió 8 COLLARES/AROS/BRAZALETES.

**No es una regresión del refactor.** En ambos turnos F-08C resolvió `cats=['CLUTCH']` con 0 candidatos y tomó `POOL_EMPTY`, que por diseño no hace nada y cae al `smart_fallback` del flujo normal (línea ~2117 del handler). El bloque inline anterior hacía exactamente lo mismo (`elif len(_c08_candidates) > 0`). Los productos vinieron de `improved_fallback_exclude_seen.py`, no tocado.

**Cadena de causa raíz:**

1. En T5 quedaba **un solo** producto CLUTCH sin mostrar; `strict_category=True` se respetó y devolvió 1/8.
2. T6 lo excluyó (`shown` 32→33) y la categoría quedó en **cero**.
3. `smart_sample_across_categories` devuelve `[]` (línea 1131) y en la línea 1947 el `else` *"Continuar con siguiente estrategia"* cae a PRIORIDAD 2, que usa preferencias históricas e **ignora `strict_category`**.
4. Resultado: 8 productos de `['COLLARES', 'AROS', 'BRAZALETES']`.

**Asimetría de la guarda:** con 1 o más productos se respeta `strict_category`; con **cero** se evade. Es la misma forma de defecto que el "caso limite 0 candidatos" corregido en F-08C el 17/06/2026 (condición `0 < len(...)` que excluía el peor escenario). **El límite inferior de un rango es donde fallan las guardas**, porque se escriben pensando en el caso típico.

**Matiz importante — el gap es conocido y está documentado.** El comentario de las líneas 2127-2141 del handler lo describe con precisión, incluido el caso CALZONES del 20/06/2026. La mitigación elegida entonces fue **detectar y avisar al LLM**, no suprimir. Y funcionó correctamente aquí: `category_exhausted_notice_added_to_prompt category=CLUTCH shown=0 total=8 off=8` y `solucion_b_suppressed_category_mismatch`. No es un bug sin detectar; es una decisión de producto pendiente de revisar (ver A.8.7).

### A.8.6 Defecto de contenido corregido: "bolsos" no alcanzaba CARTERAS — APLICADO

La categoría CLUTCH tenía 1 solo producto disponible, pero el catálogo **sí tiene carteras** (breakdown de T2: `'CARTERAS': 5`). En `CATEGORY_KEYWORDS`, `"bolso"`/`"bolsos"` estaban **solo** en CLUTCH; CARTERAS tenía únicamente `"bolso mano"`. Quien pedía "bolsos" nunca alcanzaba las carteras.

**Cambio aplicado (02/10/2026):** `"bolso", "bolsos"` añadidos a las keywords de CARTERAS en `src/recommenders/improved_fallback_exclude_seen.py`.

**Justificación de bajo riesgo:** el solapamiento ya existía en el sentido contrario — CLUTCH incluye `"cartera"`/`"carteras"`, por lo que "Muéstrame carteras" ya devolvía `['CLUTCH', 'CARTERAS']`. El cambio solo completa la simetría.

**Validación:** `ast.parse` OK; corpus de 29 queries comparado antes/después contra el archivo real del repo: cambian únicamente las 7 que contienen "bolso"/"bolsos" (`['CLUTCH']` → `['CLUTCH', 'CARTERAS']`); las otras 22 idénticas. `CATEGORY_KEYWORDS` mantiene sus 46 entradas y solo difiere en `CARTERAS`.

**Pendiente de deploy.** Tras desplegarlo, repetir el Caso 4 y esperar `cats=['CLUTCH', 'CARTERAS']` en el log `pool insuficiente`.

### A.8.7 Decisión de producto abierta

¿Basta con avisar al LLM cuando la categoría pedida queda en cero, o hay que dejar de mostrar los productos ajenos? Mostrar 8 collares a quien pidió bolsos es malo; mostrar cero y no ofrecer nada también. Ver la propuesta de "cero productos de relleno + alternativa explícita" discutida el 02/10/2026, pendiente de decisión de Yasmani.

### A.8.8 Hallazgo secundario, fuera de alcance

Las 9 llamadas al LLM fallaron contra LFM2-24B con `404 - No endpoints found for liquid/lfm-2-24b-a2b` y cayeron a GPT-4o-mini (`gpt4o_mini_fallback_ok` ×9, más `lfm_warmup_error` y `LFM keep-alive error`). El fallback funcionó, pero el modelo primario está efectivamente caído en OpenRouter. Requiere revisión propia.

---

## Addendum A.9 — Cableado de F-08 Fase A (02/10/2026): APLICADO, pendiente de deploy

Con "aplícalo" de Yasmani. Cierra el paso 1b: **las dos rutas de similitud visual comparten ya el mismo módulo**.

**Qué cambió:** el cuerpo de `if _f08_visual_ids:` (antes ~2317-2714, 398 líneas) llama a `f08_similarity_resolution` con `F08A_ROUTE`. El handler pasa de 3453 a 3331 líneas (−122). Se mantienen en el llamador la llamada FAISS con fallback CDN, `smart_fallback`, `normalize_recommendation_dict`, el `try/except` propio del relleno y **todos los logs con formato idéntico**.

**Las tres divergencias de Fase A quedan como configuración, no como flujo:** `use_query_categories=False` (nunca consulta el texto), `interleave_siblings=True` (NIVEL 1, que F-08C no tiene) y `happy_path_shortfall_signal=False` (el aviso del 26/07, que F-08C sí tiene). Corregirlas es ahora cambiar un campo, no copiar código entre bloques.

**Detalle de fidelidad que exigió cuidado:** en el bloque original el `import` de `get_parent_categories` está **dentro** del mismo `try` que la llamada, así que un `ImportError` degrada al tipo exacto en vez de perder la búsqueda visual entera (a diferencia de F-08C, donde el import ya estaba resuelto antes). Se preserva envolviendo el import en `_f08_parent_categories_fn()`, que el módulo invoca dentro de su propio `try`. Un import eager habría cambiado el comportamiento en silencio; la prueba diferencial lo detecta (ver abajo).

Se preserva igualmente el guard `and _f08_tfidf` de la partición T8, anulando el ancla de ranking cuando no hay índice TF-IDF.

**Validación:**

- **Prueba diferencial:** bloque inline anterior vs bloque nuevo, ambos ejecutados con `exec` en el mismo entorno simulado. **6.000 casos idénticos** en retorno, cada línea de log, argumentos de `smart_fallback` y `category_exhausted_info`. Cobertura: 2.629 sin retorno, 938 camino feliz, 1.162 parcial con relleno, 1.005 con agotamiento, 265 con `ImportError` simulado. Repetida tras aplicar, extrayendo el bloque **del archivo real del repo**.
- **Mutation testing:** 7/7 detectados (ruta C en vez de A → sin NIVEL 1, espacio extra en un log, `strict_category=False`, `user_query` no suprimido, debug→warning, `score_step` 0.03→0.02, e import eager que rompe la degradación).
- `ast.parse` OK; archivo byte a byte idéntico al validado en sandbox; 52/52 tests del módulo en verde (sin cambios en el módulo).

**Señal de regresión número uno tras el deploy:** `F-08 visual_search fallback a TF-IDF: <error>`. Secundaria: `F-08 partial_fill failed`.

---

## Addendum A.10 — Validación en producción de ambas rutas: **PASO 1b CERRADO** (03/10/2026)

**Corridas:** revisión `retail-recommender-00309-ldl`, dos tandas (12:56–13:15 y 13:29–13:49 UTC), 3.161 entradas de log únicas, **17 turnos** en 5 sesiones.

### A.10.1 Veredicto

**Las dos rutas de similitud visual comparten el módulo extraído y están validadas en producción. Cero regresiones** en las dos tandas: 0 `F-08 visual_search fallback`, 0 `F-08 partial_fill failed`, 0 `F-08C visual fallback`, 0 timeouts, 0 `ImportError`, 0 `UnboundLocalError`, 0 ERROR/CRITICAL. Todos los `candidate breakdown` cuadran (suma == `total=`).

### A.10.2 Cobertura: los cinco caminos del módulo, ejercitados

| Camino | Estado | Evidencia |
|---|---|---|
| `POOL_HAPPY` sin aviso | Cubierto | AROS, CAPAS BORDADAS, COLLARES, KIMONOS, CARTERAS, CAPAS BORDADAS (F-08C) |
| `POOL_PARTIAL` con relleno completo | Cubierto | KIMONOS 4+4 (Fase A); CARTERAS 4+4 (Fase A); PANTALONES 1+7 (F-08C); ALAS DE NOVIA 7+1 (F-08C) |
| `POOL_PARTIAL` **con agotamiento** | Cubierto | PANTALONES 4+1=5 (Fase A, 13:48:34) |
| `POOL_EMPTY` | Cubierto | COLLARES+"bolsos"; PANTALONES shown=13 |
| Resolución de categorías: `parent_group`, `exact_type`, `query_text` con y sin ranking | Cubiertas las 4 | — |

**Pendientes de observar en producción** (cubiertos por 46.000 casos sintéticos y 52 tests): `detect_happy_path_shortfall` (solo F-08C) y el efecto observable del intercalado NIVEL 1.

### A.10.3 Coincidencia numérica módulo vs producción

Dos turnos de relleno parcial se contrastaron función a función:

| Turno | Eventos sintéticos | Exclusiones | `category_exhausted_info` |
|---|---|---|---|
| KIMONOS 13:14:37 (Fase A) | módulo 2 = log "con 2 eventos" | módulo 5 = log "5 from context" | `None` = sin línea de agotamiento |
| PANTALONES 13:48:34 (Fase A) | módulo 2 = log "con 2 eventos" | módulo 5 = log "5 from context" | módulo `{'PANTALONES', 5, 5}` = log "4 visual + 1 fill = 5" |

En PANTALONES se devolvieron **5 productos, no 8**: `strict_category` respetado, sin relleno con categorías ajenas (`off=0` en el aviso al LLM).

### A.10.4 Fix de CARTERAS validado — y con un efecto de segundo orden

Mismo escenario que el fallo del 02/10 (ancla COLLARES + "Muéstrame bolsos similares a este", pool visual 0):

| | 02/10 (antes) | 03/10 (después) |
|---|---|---|
| Categorías detectadas | `['CLUTCH']` | `['CLUTCH', 'CARTERAS']` |
| Resultado | 8 productos de **otras** categorías | 5 de la categoría pedida |
| Aviso al LLM | `shown=0 total=8 off=8` | `shown=5 total=5 **off=0**` |

**Efecto de segundo orden:** al existir ahora productos alcanzables, `query_driven_products` deja de estar vacío y el flujo **nunca llega** al `else` de la línea 1947 que evade `strict_category`. El defecto D2 (A.8.5) queda **enmascarado, no resuelto**: si CLUTCH y CARTERAS se agotaran ambos, volvería a dispararse.

### A.10.5 Gap nuevo detectado: las anclas nunca entran en `shown_products`

**Síntoma reportado por Yasmani:** estando en la página de un producto, el sistema se lo recomendó de vuelta.

**Verificación:** en los 10 turnos de la segunda tanda, el `product_id` del ancla **nunca** aparece entre sus propias recomendaciones. La exclusión del ancla funciona en ambas rutas.

**Lo que sí ocurrió** (sesión PANTALONES):

| Turno | Ancla del widget | ¿Devolvió `9978594394421`? |
|---|---|---|
| 13:48:34 | **9978594394421** (Palazzo Ariel Satin Negro) | no — es el ancla |
| 13:48:51 | 9978565034293 (Palazzo Claudia Negro) | **sí, posición 1** |
| 13:49:12 | 9978594394421 | no — vuelve a ser el ancla |

El usuario aterrizó en *Palazzo Ariel Satin Negro*; al hacer clic en una tarjeta el contexto del widget se movió a otro producto mientras la página seguía siendo la misma, y el turno siguiente le recomendó lo que tenía delante.

**Causa raíz** (`mcp_conversation_handler.py` ~851-885, fuera de los bloques refactorizados): `shown_products` se construye **solo** con `turn.recommendations_provided`. Las anclas nunca se añaden, así que un producto que fue ancla vuelve a ser elegible en cuanto el contexto se mueve. **Gap preexistente, no regresión.**

**Propuesta, no aplicada:** añadir el ancla de cada turno a `shown_products`. Requiere decisión por el tamaño del catálogo: en esa misma sesión, con `shown=13`, el pool ya quedó en 0.

### A.10.6 El bug de etiqueta A.3.a sigue latente — condición exacta para verlo

En PANTALONES la etiqueta fue `'PANTALONES'`, **correcta**, porque ese tipo no tiene grupo padre y `cats[0]` coincide con el ancla. Para que el bug se manifieste hace falta un ancla **con grupo padre** Y relleno insuficiente. Verificado con el módulo: con ancla CARTERAS (9 hermanas), de haberse agotado el relleno la etiqueta habría sido **`'AROS'`**.

### A.10.7 Evidencia de producción que justifica portar NIVEL 1 a F-08C

Turno 13:49:53, ancla ALAS DE NOVIA en F-08C: breakdown `{'AROS': 4, 'CINTURONES': 2, 'TOCADOS': 1}` — **cero del tipo propio y tres tipos hermanos**. Como F-08C no tiene intercalado, el orden es similitud visual pura y los 4 aros van primero. Con el intercalado de Fase A sería aro, cinturón, tocado, aro, cinturón, aro, aro. Para alguien eligiendo complementos de novia, la segunda ordenación es claramente mejor. Es el caso real que justifica la propagación en el paso 2.

### A.10.8 Hallazgo de contenido: la familia `outerwear` no tiene steering text

Dos anclas KIMONOS dieron purezas de pool opuestas: 22 de 30 vecinos (73%) con una, 4 de 30 (13%) con un "Maxi Tapado Gala Velvet Dorado Claro". Verificado en `product_taxonomy.py`: KIMONOS, CAPAS GASA y CAPAS BORDADAS tienen `steering=NO` y `alpha_reinforce=None`, mientras que los accesorios sí están calibrados desde Fase 1b. Candidato a la siguiente ronda de calibración con `fase0_poc.py`.

### A.10.9 Estado del paso 1

**CERRADO.** Módulo extraído, dos rutas cableadas, 52 tests de caracterización, oráculo de equivalencia, y los cinco caminos validados con tráfico real. El handler pasó de 3.687 a 3.331 líneas (−356). Las divergencias entre rutas son ahora campos de `SimilarityRouteConfig`, no código duplicado. **El paso 2 queda abierto** con las prioridades de A.10.5, A.10.6 y A.10.7.

---

## Addendum A.11 — Backlog consolidado de gaps abiertos (06/10/2026)

Estado **verificado contra el código real**, no de memoria, antes de abrir el diseño del contrato de recomendaciones. Cada gap lleva su evidencia y dónde vive.

### A.11.1 Gaps estructurales — los absorbe el diseno del contrato `principal` / `alternativas`

| # | Gap | Evidencia | Dónde vive |
|---|---|---|---|
| E1 | **Una sola lista plana con tres fuentes incompatibles** (pool visual, catalogo por categoria, preferencias historicas) bajo la misma etiqueta "RECOMENDADO PARA TI" | Sesion 05/10, 8 turnos | Contrato de salida handler -> widget |
| E2 | **Un item de categoria ajena puede superar en ranking a uno de la categoria pedida** | 05/10: Cinturon Ramana pos.5 por encima de Clutch Antonieta pos.6 | Rama `POOL_PARTIAL`: visual arranca en 1.0, relleno en `last-0.05` |
| E3 | **El "% match" no mide parecido: es la posicion de llenado** | Pantalla 100/98/96/94/92/87/85/83 = 1.0 menos `score_step`, con salto 0.05 al empezar el relleno | `normalize_recommendation_dict` + widget |
| E4 | **El caso mas frecuente de mezcla no emite ninguna senal**: relleno que SI completa con candidatos visuales de categorias ajenas | 05/10: 1 aviso en 8 turnos; el LLM no menciona la mezcla en los otros 7 | No existe emisor para ese caso |
| E5 | **El filtro de categoria se aplica DESPUES del recorte top_k** | 05/10: con shown=80, el pool de 50 dio 0 CARTERAS mientras el catalogo SI tenia (ningun `preferred exhausted` en 1.532 lineas) | `colbert_client` + handler |

**Nota sobre E4:** el fix del 04/10 (senal sobrecargada, A.10 + paso 2) resolvio que el LLM **afirmara en falso** el agotamiento. NO resolvio que **revele** la mezcla: en el turno del 05/10 donde si se emitio la senal, el LLM tampoco la menciono pese a pedirselo el prompt. Confirma que instruir al redactor no es un mecanismo fiable de revelacion; la estructura si lo es.

### A.11.2 Gaps de comportamiento — independientes del contrato

| # | Gap | Estado verificado | Prioridad sugerida |
|---|---|---|---|
| B1 | **Las anclas nunca entran en `shown_products`** -> el producto que el usuario tiene delante se le puede recomendar | `shown_products.update(recs)` existe; ninguna adicion del ancla. GAP VIVO | Alta, coste muy bajo |
| B2 | **D2: `strict_category` se evade cuando la categoria queda en CERO** -> rellena con preferencias historicas | `# Continuar con siguiente estrategia` sigue en `improved_fallback_exclude_seen.py` l.1965 y 1968. VIVO, solo enmascarado por el fix de CARTERAS | Alta |
| B3 | **Intercalado NIVEL 1 ausente en F-08C** | `F08C_ROUTE.interleave_siblings=False` | Media (evidencia A.10.7) |
| B4 | **Aviso de camino feliz ausente en Fase A** | `F08A_ROUTE.happy_path_shortfall_signal=False` | Media |
| B5 | **Bug A.3.a: etiqueta = primer hermano, no el ancla** | `build_partial_exhaustion_info(['CAPAS BORDADAS','CAPAS GASA'],2,1,6)` -> `'CAPAS BORDADAS'`. VIVO | Media, coste trivial |
| B6 | **Desempate ACCESSORIES/JOYAS por orden de insercion del dict** | Contrato implicito no documentado | Baja, decision de producto |
| B7 | **Fase A nunca consulta el texto de la query** | `F08A_ROUTE.use_query_categories=False` | Baja, decision de producto |

### A.11.3 Gaps de contenido y plataforma

| # | Gap | Evidencia |
|---|---|---|
| C1 | **La familia `outerwear` no tiene steering text** (KIMONOS, CAPAS GASA, CAPAS BORDADAS): `alpha_reinforce=None` | 03/10: dos anclas KIMONOS con pureza de pool 73% vs 13% |
| C2 | **LFM2-24B devuelve 404 en OpenRouter** (`No endpoints found for liquid/lfm-2-24b-a2b`); 100% de las llamadas caen a GPT-4o-mini | Observado en las 4 sesiones del 02 al 05/10 |

### A.11.4 Validaciones pendientes en produccion

Todo lo demas del modulo esta cubierto con trafico real (A.10.2 + el aviso de camino feliz, confirmado el 04/10 y el 05/10).

| Comportamiento | Condicion necesaria para observarlo |
|---|---|
| **Bug A.3.a** (B5) | Ancla de una categoria **con grupo padre** Y relleno insuficiente a la vez. Tres intentos fallidos: pantalones no tiene familia; capas y carteras no agotaron el relleno |
| **Efecto observable del intercalado NIVEL 1** | Ancla con **menos de 8 del tipo propio** en el pool Y **al menos dos tipos hermanos** presentes |
| Control negativo de Fase A (consulta sin patron de similitud en Turn 1) | Trivial, nunca ejecutado |

**Nota:** B5 y el efecto de NIVEL 1 quedan cubiertos por los 52+ tests y el oraculo de 40.000 casos; lo que falta es solo la observacion en produccion.

### A.11.5 Decision estrategica (06/10/2026)

Se prioriza el **contrato de datos** (`principal` / `alternativas`) sobre la mejora de la recuperacion. Razon: la estructura es el invariante, la calidad del pool es lo que se ajusta de forma continua. Mejorar primero la recuperacion reduce la *frecuencia* de una experiencia deshonesta sin eliminarla; fijar primero la estructura hace que el peor caso ya sea honesto y que cada mejora posterior del pool solo agrande el bloque principal.

**Especificacion resultante:** `Composite_Embedding_Granular/SPEC_Contrato_Recomendaciones_06102026.md` (06/10/2026). Cubre el contrato completo, las reglas de particion por intencion, la migracion en 4 fases, el UX de separacion de bloques y el reinicio de catalogo, y la relacion con `BACKLOG_Busqueda_por_Atributos_Color_24072026.md`. Los gaps E1-E4 de A.11.1 quedan asignados a esa spec; E5 queda explicitamente fuera de su alcance.

---

## Addendum A.12 — Auditoría de estado y cierre documental (08/10/2026)

Estado **verificado ejecutando el código real**, gap por gap, no de memoria. Sustituye a A.11 como foto válida.

### A.12.1 Entregado desde A.11

| | Qué | Estado |
|---|---|---|
| Contrato `principal`/`alternatives` | Módulo + 48 tests | Hecho |
| Familias de similitud (G2) | `SIMILARITY_FAMILIES`, 7 familias + 41 tests | Hecho |
| Catalogar antes que rellenar (G1) | Caminos parcial y vacío en F-08C | Hecho |
| Nivel 1 del pool | `visual_pool_size`, pool crece con lo visto | Hecho |
| Puntuaciones reales | Servicio + cliente; widget pendiente | Hecho (backend) |
| Señal sobrecargada | `kind` distingue agotamiento de mezcla | Hecho |
| Etiqueta A.3.a (B5) | Resuelta **en F-08C** vía familia con ancla primero | Parcial |

**Evidencia de producción (08/10, revisión `00313-bjv`):** siete turnos consecutivos con `principal=8['CARTERAS'] alternatives=0[]`, frente a mezcla desde T8 el 07/10. En T9, con 3 bolsos en el pool y 21 joyas, fue al catálogo pidiendo la familia y devolvió 8 bolsos.

### A.12.2 Gaps abiertos, por prioridad

| # | Gap | Estado verificado | Notas |
|---|---|---|---|
| **G4** | El motor no consume `to_prompt_facts()` | ABIERTO | **El asistente sigue sin avisar de la mezcla.** Es lo que más nota el usuario |
| **G3** | Fase A sin contrato | ABIERTO | El turno 1 no particiona; E2 vive ahí todavía |
| **B1** | Las anclas no entran en `shown_products` | ABIERTO | Se puede recomendar el producto que el usuario tiene delante |
| **B2** | `strict_category` se evade en cero | ABIERTO | `# Continuar con siguiente estrategia`, líneas 1965 y 1968 |
| **E3** | El widget muestra el `% match` posicional | ABIERTO | Las puntuaciones reales ya llegan al cliente; falta fase 3-4 |
| **E1** | API y widget sin bloques | ABIERTO | Fases 3 y 4 |
| **E5** | Filtro de categoría tras el recorte | Nivel 1 hecho; 2 y 3 abiertos | La ruta outfit ya tiene el mecanismo (A.11 / 2.4 de la spec) |
| **B3** | Intercalado NIVEL 1 ausente en F-08C | ABIERTO | **Cambió de alcance con G1:** ya no afecta al bloque principal (homogéneo por construcción), solo al orden dentro de las alternativas |
| **B5** | Etiqueta por `categories[0]` | Resuelto en F-08C, ABIERTO en Fase A | Se cierra con G3 |
| **B6** | ACCESSORIES/JOYAS | ABIERTO, documentado | Ver A.12.4 |
| **B7** | Fase A ignora el texto de la consulta | ABIERTO | Decisión de producto pendiente |
| **C1** | `outerwear` sin steering text | ABIERTO | Reconfirmado hoy: KIMONOS y CHAQUETAS **tampoco tienen grupo padre** |
| **C2** | LFM2-24B devuelve 404 | ABIERTO | 100% de fallback a GPT-4o-mini desde el 02/10 |
| **nuevo** | `BRAZALETE` singular: 1 producto | ABIERTO | Consultado en Shopify el 08/10. La familia ya lo cubre; es higiene de datos |

### A.12.3 Variables de entorno — referencia

Las cuatro son **opcionales**; sin ninguna, el sistema usa los valores por defecto. Son palancas de marcha atrás: se cambian en Cloud Run y aplican **sin redesplegar**, porque se leen en cada llamada y no en el default de una firma.

| Variable | Qué controla | Default |
|---|---|---|
| `RECS_PRINCIPAL_FIRST` | G1: ir al catálogo cuando falta lo pedido. `0` revierte G1 entero | activado |
| `RECS_VISUAL_POOL_BASE` | Vecinos a pedir de entrada; una sola variable para ambas rutas | 30 (Fase A) / 50 (F-08C) |
| `RECS_VISUAL_POOL_CAP` | Techo del pool tras sumar lo ya mostrado | 200 |
| `RECS_MAX_ALTERNATIVES` | Tope de alternativas; `0` las desactiva | 8 (objetivo 4) |

`MAX_ALTERNATIVES_TARGET` **no es** variable de entorno: es una constante que deja escrito que el objetivo son 4 mientras el valor en vigor sea 8.

Referencia autoritativa en código: docstring de `src/recommenders/f08_similarity_resolution.py`.

### A.12.4 Contrato implícito ACCESSORIES/JOYAS — documentado, no resuelto

AROS, COLLARES, BRAZALETES y BRAZALETE pertenecen a los dos grupos. Gana ACCESSORIES solo por orden de inserción del diccionario.

**Su alcance se redujo con G2.** Verificado hoy con ancla AROS: reordenar el diccionario cambiaría el **pool** de 9 tipos a 4, pero **lo pedido sigue siendo `['AROS']`** en ambos casos. El conflicto ya no puede alterar la respuesta a lo que el usuario pidió; solo cuánto material queda para alternativas.

**Decisión: no se arregla ahora.** El arreglo correcto es decidir explícitamente qué entra en el pool, y eso es el nivel 2 del plan E5. Tocarlo antes sería un parche sobre un mecanismo que se va a sustituir. Además, el 08/10 el solapamiento jugó **a favor**: gracias a los 9 tipos hubo material para alternativas en los turnos finales.

Documentado en el docstring de `get_parent_categories()`, con la advertencia de no reordenar y qué test actualizar si alguien lo cambia.

### A.12.5 Deuda creada por G1 — anotada para no repetir el error del 01/10

G1 dejó **código y configuración sin efecto**:

- `detect_happy_path_shortfall()` ya **no se llama desde ninguna ruta**.
- `F08C_ROUTE.happy_path_shortfall_signal = True` **ya no describe el comportamiento**: el flag dice que la ruta emite el aviso y el código no lo hace.

Ambos quedan marcados en el código como superseded, con la condición para eliminarlos: **cuando Fase A esté cableada (G3), los dos se borran juntos.**

Se documenta en vez de borrarse ya porque la migración está a medias. El motivo de documentarlo con tanto detalle es directo: **una nota que contradice al código es peor que no tener nota**, y fue exactamente lo que provocó el diagnóstico erróneo que abrió esta sesión (A.1).

### A.12.6 Lecciones de oráculo acumuladas

Tres fallos de oráculo en esta sesión, todos detectados por mutation testing y ninguno por los tests:

| Fecha | Fallo | Corrección |
|---|---|---|
| 06/10 | I2 derivaba "lo pedido" **del objeto bajo prueba**; un mutante que lo ensanchaba arrastraba al oráculo | I6: derivar de las entradas |
| 07/10 | I11 leía el tamaño pedido **del log**, que refleja la mutación | Calcularlo desde `n` y el reparto |
| 08/10 | Las invariantes empezaban con `if rset is None: continue`, **saltando en silencio los casos sin contrato** — ocultó un día entero que el camino vacío no lo construía | I12: exigir contrato si hubo candidatos |

Patrón común: **el test no mira donde está el problema**, sea porque toma la expectativa de la salida o porque excluye los casos problemáticos. La defensa es el mutation testing, y la pregunta obligada ante cualquier filtro en un oráculo: *¿y si el fallo consiste precisamente en caer en la categoría que estoy descartando?*

### A.12.7 Orden recomendado

1. **G4** (fase 2): el motor consume `to_prompt_facts()`. Es lo único que falta para que el asistente **diga la verdad** sobre la mezcla, y la señal ya es correcta desde hoy.
2. **G3**: Fase A al contrato. Cierra E2 en el turno 1, cierra B5 y permite borrar la deuda de A.12.5.
3. **B1**: anclas a `shown_products`. Barato y muy visible.
4. **B2**: evasión de `strict_category` en cero.
5. **E3 / E1**: fases 3 y 4, con frontend.
6. **C1**: calibración de `outerwear`, sprint propio con medición.

---

## Addendum A.13 — Validación del lote grande (12/10/2026)

**Corrida:** revisión `retail-recommender-00321-h9q`, 5 consultas, 1.409 entradas únicas. **Cero regresiones** (0 `visual fallback`, 0 `partial_fill failed`, 0 `ImportError`, 0 `UnboundLocalError`, 0 ERROR/CRITICAL).

### A.13.1 Qué cubrió cada turno

| Turno | Consulta | Ruta | Qué valida |
|---|---|---|---|
| T1 | "muestrame pantalones" | consulta por categoría, sin ancla | — |
| **T2** | similares a un pantalón | **F-08C**, camino vacío | **mapa de alternativas, filtro del pool, defensa B2, rama vacía** |
| T3 | similares a unos aros | F-08C, camino feliz | contrato con bloque puro |
| T4, T5 | "accesorios que combinen" | **F-08B** (outfit) | intención detectada correctamente, ruta distinta |

### A.13.2 T2 — el turno que valida el lote

```
F-08C candidate breakdown: {'FALDAS': 13} (anchor_type='PANTALONES', total=13)
F-08C reparto: pedido=['PANTALONES'] en_pool=0 otros=13 camino=empty
   Preferred categories: ['PANTALONES']
   Using diverse category recommendations        <- B2 se dispara
   Generated 8 diverse recommendations           <- 8 productos ajenos
F-08C category_exhausted (pool sin nada de lo pedido): 0 visual + 0 fill
F-08C pool_sin_lo_pedido: 13 productos (catalogo=0, alt=13)
F-08C contrato: principal=0[] alternatives=6['FALDAS'] exhausted=True
```

Cuatro cosas se validan de una vez:

1. **Filtro del pool = familia + alternativas.** El desglose trae **13 FALDAS** con ancla PANTALONES. Con el filtro anterior (grupo padre de PANTALONES = `['PANTALONES']`) las faldas se habrían excluido y `total` sería 0. Es la prueba directa de que el criterio nuevo está activo.
2. **Mapa de alternativas.** `alternatives=['FALDAS']` es exactamente la decisión de producto del 10/10. Antes este tipo no podía tener alternativas.
3. **Defensa B2.** `smart_fallback` se saltó `strict_category` y devolvió 8 productos "diverse", y `filter_fill_to_request` los descartó todos → `catalogo=0`. **Es justo el camino por el que el 10/10 se coló ropa interior sin stock.** Hoy no llega nada.
4. **Rama vacía + `exhausted`.** Se construye el contrato en vez de caer al fallback genérico, y `exhausted=True` llega al motor.

### A.13.3 Tope de alternativas: 6 en vigor

Con 13 candidatos y `principal=0`, el contrato devolvió `alternatives=6`. Confirma que `RECS_MAX_ALTERNATIVES=6` está configurado y que la variable actúa sin redesplegar.

### A.13.4 Gaps de validación de esta corrida

| | Estado |
|---|---|
| **Fase A (G3) NO se ejercitó** | 0 líneas `F-08` sin C en toda la corrida. T1 no tenía ancla y T2-T5 fueron turno 2+ |
| Camino parcial con alternativas | no cubierto (T2 fue vacío, T3 feliz) |
| Ancla con familia multi-tipo (bolsos) | no cubierto en esta corrida |

**Cómo cerrarlos:** abrir una sesión **nueva** (para que `shown_products` esté vacío) y pedir similares a un pantalón **en el primer turno**. Debe aparecer `F-08 reparto:` y `F-08 contrato:`, sin la C.

### A.13.5 Defecto menor detectado: log de expansión engañoso

En T3, con ancla AROS:

```
F-08C category expansion: 'AROS' -> [9 tipos del grupo padre]
```

Ese log sigue imprimiendo el **grupo padre**, pero desde el 10/10 el filtro del pool usa `familia + alternativas` — para AROS, 4 tipos, no 9. El log ya no describe lo que hace el código.

No afecta al comportamiento, pero es exactamente el tipo de nota que provocó el diagnóstico erróneo de A.1. **Debe corregirse para imprimir `_c08_pool_cats`.**

### A.13.6 Estado de fases

| Fase / gap | Estado |
|---|---|
| Contrato `principal`/`alternatives` (F-08C) | **Validado en producción** |
| G1 catalogar antes que rellenar | **Validado** (parcial 08/10, vacío 10/10 y 12/10) |
| G2 familias de similitud | **Validado** |
| G4 / fase 2 — el motor consume `to_prompt_facts()` | **Validado** |
| Nivel 1 del pool | **Validado** |
| Defensa B2 | **Validado** (12/10, T2) |
| Mapa de alternativas + filtro del pool | **Validado** (12/10, T2) |
| Rama vacía devuelve contrato | **Validado** (12/10, T2) |
| Puntuaciones reales | Backend validado; **el widget aún no las usa** |
| **G3 Fase A al contrato** | Desplegado, **sin ejercitar** |
| Fases 3 y 4 (widget) | No iniciadas |

---

## Addendum A.14 — Fase A validada; B1 reproducido (13/10/2026)

**Corrida:** revisión `00321-h9q`, sesión **nueva**, 4 consultas, 660 entradas. Cero regresiones.

### A.14.1 G3 VALIDADO — Fase A con contrato, en el turno 1

```
F-08 candidate breakdown: {'PANTALONES': 5, 'FALDAS': 2} (anchor_type='PANTALONES', total=7)
F-08 reparto: pedido=['PANTALONES'] en_pool=5 otros=2 camino=partial
F-08 category_exhausted: 5 visual + 0 fill = 5 (categoria='PANTALONES')
F-08 visual_partial_plus_fill: 7 productos (visual=5, fill=0, alt=2, needed_fill=3)
F-08 contrato: principal=5['PANTALONES'] alternatives=2['FALDAS'] exhausted=True
```

Son líneas `F-08` **sin la C**: la ruta del primer turno. Cierra el último gap de validación del backend.

Y de paso cubre el **camino parcial con alternativas**, que tampoco se había ejercitado: 5 pantalones de principal y 2 faldas de alternativa, en el mismo turno. La etiqueta de agotamiento dice `PANTALONES`, el tipo del ancla — **bug B5 (A.3.a) confirmado como cerrado también en Fase A**.

Los cuatro turnos cubrieron los tres caminos: parcial con alternativas (T1, T2), outfit (T3) y vacío (T4).

### A.14.2 B1 reproducido en vivo — el ancla vuelve como recomendación

| Turno | Ancla | Observación |
|---|---|---|
| T1 | Palazzo Silvia (`...329205`) | aterrizaje |
| T2 | Palazzo Ariel | **recomienda Palazzo Silvia**, el ancla de T1 |
| T4 | **Palazzo Silvia** | el usuario acaba viendo el producto del que partió |

`shown_products` solo recoge `recommendations_provided`; las anclas nunca entran. Con 6 pantalones en catálogo el efecto es inmediato: el único pantalón "sin mostrar" en T2 era precisamente el de partida.

Gap conocido desde el 03/10 (A.10.5), nunca corregido. **Sube a prioridad alta:** con el catálogo pequeño de algunos tipos no es un caso raro, es el caso normal.

### A.14.3 Segundo log engañoso, corregido

```
F-08 pool ampliado: top_k=100 (base=30, shown=0)
```

Aritméticamente falso: 30 + 0 no es 100. El log imprimía el `faiss_top_k` de la ruta en vez de la base **efectiva**, que con `RECS_VISUAL_POOL_BASE=100` es 100. Corregido en ambas rutas para usar la base efectiva; así el log deja además de emitirse cuando no hay ampliación real.

Es el segundo log que se desincroniza del código en dos días (el otro, A.13.5). Ambos aparecieron al hacer configurable algo que antes era constante: **cuando un valor pasa a ser configurable, todo log que lo mencione hay que revisarlo**, porque seguía imprimiendo la constante.

### A.14.4 Estado del backend

Todo el trabajo de backend de estas dos semanas queda **validado en producción**: contrato en las dos rutas, G1, G2, G4, nivel 1, defensa B2, mapa de alternativas, filtro del pool, rama vacía y `exhausted`.

Queda fuera: fases 3 y 4 (widget), B1, B2 de raíz y C1.

---

## Addendum A.15 — Fases 3 y 4, B1 y reinicio por categoría (13–17/10/2026)

Cinco días de trabajo, todo **validado en producción**. Revisiones `00321-h9q` → `00327-qnl`.

### A.15.1 Entregado

| Pieza | Qué hace | Validado |
|---|---|---|
| **B1** — anclas a "ya visto" | El producto que el usuario tiene delante deja de recomendarse | 15/10 |
| **Fase 3.1** — API con bloques | `recommendation_blocks` con ids, no copias de productos | 15/10 |
| **Fase 3.2** — widget con dos bloques | "Similares a este" / "También podría combinar" | 15/10 |
| **Fase 4** — `% match` verdadero | Solo donde hay `visual_score`; el resto sin número | 15/10 |
| Jerarquía visual | Alternativas más pequeñas, atenuadas, con entrada retrasada | 16/10 |
| **Reinicio por categoría** | Botón funcional, alcance por categoría | 17/10 |
| UX del reinicio | Burbuja con la acción real, aviso del asistente, botón al final y solo en el último turno | 17/10 |

### A.15.2 Diseño del reinicio por categoría

`shown_products` **no se almacena**: se deriva de los turnos. Así que reiniciar no puede ser borrar nada; es marcar **desde cuándo** vuelven a contar.

```python
MCPConversationContext.category_resets: Dict[str, float]   # {"PANTALONES": 1760...}
```

Un producto se ignora si su categoría tiene una marca posterior al turno que lo mostró. **Marca temporal y no lista de ids perdonados**, porque se mantiene sola: con una lista habría que limpiarla al volver a mostrarlos o el usuario vería los mismos productos en bucle.

La petición viaja como **campo** (`reset_category`) en la consulta normal, no como endpoint aparte: se aplica antes de calcular, así que el mismo turno devuelve ya los productos renovados.

Evidencia (17/10):
```
reinicio por categoria registrado: PANTALONES
   5 productos de este turno vuelven a estar disponibles
   ancla 9978594394421 vuelve a estar disponible
F-08C contrato: principal=5['PANTALONES'] alternatives=1['FALDAS'] exhausted=True
```

### A.15.3 Cinco fallos encontrados por el camino

Todos reales, todos corregidos, y los cinco comparten una propiedad: **fallaban en silencio**.

| # | Fallo | Por qué no se vio |
|---|---|---|
| 1 | B1 guardaba el **handle**, no el id numérico | Ambos son `str`; `set.add()` acepta cualquier cosa y `in` devuelve `False` sin avisar. El log parecía correcto |
| 2 | La descripción se buscaba en la raíz del item, pero vive en `product_data` | Llega vacía, no ausente: indistinguible de "este producto no tiene descripción" |
| 3 | El mensaje `I found 0 recommendations` en inglés | Marcador de depuración que la personalización sobrescribe… salvo cuando no hay productos, porque la condición exigía `base_recommendations` |
| 4 | El botón no se pintaba con cero productos | Todo el bloque dependía de `recommendations.length > 0` |
| 5 | La variante compacta se escribió en `ProductCard.module.css` | El componente importa `ProductCard_V.module.css`; el otro lleva meses comentado |

Medidas permanentes que dejaron:
- `_turn_from_dict()` filtra claves desconocidas — elimina el riesgo de que añadir un campo al dataclass haga **irreversible** el despliegue (se avanza bien, se retrocede con `TypeError`).
- Guarda de formato en el ancla: rechaza lo que no sea numérico y lo registra.
- El marcador de `ai_response` ahora está en español y es presentable si vuelve a aflorar.

### A.15.4 Lecciones de verificación

**Verificar por el VALOR, no por el identificador.** Comprobé que `cardCompact` estuviera en el bundle y lo di por bueno; la cadena venía del JavaScript, no del CSS. `styles.cardCompact` compila igual aunque la clase no exista — vale `undefined` y no aplica nada, sin error en ningún momento. Buscar `232px` lo habría detectado al instante.

**Mirar primero si hay consumidor.** Dos ciclos arreglando el transporte de la descripción cuando el componente la tenía comentada desde abril. Cuando algo no aparece en pantalla, el orden barato es el inverso: primero el render, luego el dato.

**Un efecto imperceptible equivale a uno inexistente.** La saturación al 92%, un punto de tipografía y 120 ms de retraso estaban correctamente compilados y no se veían. Calibrar es mirar la pantalla, no el editor.

**El orden de despliegue del frontend importa.** El bundle viaja dentro de la imagen (`COPY static/`), así que compilar **después** de desplegar deja el contenedor con el bundle viejo. Y si el tema de Shopify define `scriptUrl`, el navegador carga desde el CDN y el backend es irrelevante: hay que subirlo ahí también.

### A.15.5 Decisión: el bundle sigue sirviéndose desde Shopify

Se evaluó quitar `scriptUrl` para que el widget cargara del backend y el despliegue fuera uno solo. **Se descartó.** El bundle se descarga en **cada carga de página de la tienda**, no solo al abrir el chat: servirlo desde Cloud Run expondría a todos los visitantes a la latencia transatlántica y a un posible arranque en frío. Un CDN no tiene ese problema. La decisión original era correcta.

Lo que sí resuelve el problema real — que es de coordinación, no de rendimiento — es un script de despliegue que compile, **verifique por valor** y suba, en ese orden.

### A.15.6 Decisiones de producto del período

- **Tope de alternativas: 4 → 6.** Con dos bloques separados y con título, confundir una alternativa con lo pedido es mucho menos probable que en una lista plana.
- **Descripción solo en modo expandido** (17/10). En el carrusel contraído aprieta la tarjeta — la razón de quitarla en abril sigue vigente ahí. En el bloque de alternativas no se muestra nunca.
- **El botón de reinicio va al final** del bloque de alternativas y **solo en el último turno**: es una acción del momento, no parte del historial.
- **Textos de cabecera en el frontend**, deducidos de `intent`. El backend manda el dato; la redacción es presentación.

### A.15.7 Estado y pendientes

**Backend y frontend del contrato: completos y validados.**

| Gap | Estado |
|---|---|
| **Descripción tras re-sincronizar** | Abierto. Los productos tienen `descriptionHtml` en Shopify pero dejó de verse tras un re-sync; hipótesis: el índice en memoria no conserva `body_html`. **Sin confirmar** |
| **B2 de raíz** | Abierto. Contenido en la frontera de las dos rutas de similitud; vivo en outfit y estándar |
| **C1** — `outerwear` sin steering text | Abierto, sprint propio con medición |
| **E5 niveles 2 y 3** | Abierto. El nivel 2 retiraría el contrato implícito ACCESSORIES/JOYAS |
| **B7** — Fase A ignora el texto de la consulta | Abierto, decisión de producto |
| LFM2-24B devuelve 404 | Abierto desde el 02/10; 100% de fallback a GPT-4o-mini |
| `REDIS MISS` perdiendo sesiones | Visto el 15/10; sin diagnosticar |
| Asimetría joyería/complementos | Un clutch ofrece aros, unos aros ya no ofrecen clutch. Marcado en el código, a decidir con la pantalla delante |
| `BRAZALETE` singular | 1 producto en Shopify; la familia ya lo cubre. Higiene de datos |

---

## Addendum A.16 — B2 cerrado de raíz; cierre del ciclo (17/10/2026)

**Corrida:** revisión `00328-44n`, 7 consultas, 1.767 entradas. **Cero regresiones.**

### A.16.1 B2 validado — el defecto más antiguo del backlog

La guarda nueva actuó **tres veces**, y la señal que la acompaña es la que importa:

```
✅ strict_category=True: las estrategias con coherencia de categoria
   (P1 query-driven, P2 historial) no encontraron nada.
   NO se amplia a diverse/popular -- devolviendo []
```

| | Antes (10/10) | Ahora |
|---|---|---|
| `Using diverse category recommendations` en similitud | aparecía | **0 veces** |
| Productos de categorías ajenas en el relleno | 8 | **0** |

El defecto estaba en **dos** sitios, no en uno: las estrategias dirigida-por-consulta e historial manejaban bien el caso **parcial** y dejaban caer el **vacío** (`if query_driven_products:` ... else → continúa; `if personalized_products:` sin else → continúa). La guarda se colocó en la **frontera** entre las estrategias que respetan la categoría y las que no, de modo que una quinta estrategia futura queda cubierta sin que nadie se acuerde.

`filter_fill_to_request` (10/10) se mantiene como defensa en profundidad: ya no debería activarse nunca, y si lo hace, señala que algo nuevo se rompió.

### A.16.2 Los siete turnos

| Turno | Ruta | Resultado |
|---|---|---|
| T1 | Fase A, parcial | `principal=5['PANTALONES'] alternatives=2['FALDAS'] exhausted=True` |
| T2 | F-08C, feliz | `principal=8['FALDAS'] alternatives=0 exhausted=False` |
| T3 | F-08C, vacío | `principal=0 alternatives=8['FALDAS'] exhausted=True` |
| T4 | **reinicio + parcial** | reset aplicado → `principal=5 alternatives=3 exhausted=True` |
| T5, T6 | F-08B outfit | 8 productos de bag/accessory/outerwear/shoes/top |
| T7 | Estándar (categoría) | 8 query-driven |

Las tres rutas con sus cuatro caminos, el reinicio y el consumo de hechos por el motor (`prompt_facts_from_contract` en los cuatro turnos con contrato), todo en una sola sesión.

T2 no emite `contract_closing_instruction_applied`, y es correcto: con `exhausted=False` y cero alternativas no hay nada que reportar, así que se usa el cierre genérico.

### A.16.3 Hipótesis de la descripción: REFUTADA

Se sospechó que una re-sincronización del catálogo había dejado el índice en memoria sin `body_html`. **Falso.** Verificado en `tfidf_recommender.py`: `product_data` guarda el producto crudo completo ("todos los demás campos intactos: tags, body_html, variants") e `id_index` mapea `str(id)` al mismo objeto, sin copiar ni recortar.

La causa real fue que el render estaba **comentado en el frontend** por decisión de producto. La correlación que llevó a la hipótesis equivocada — los precios también habían cambiado — era casual.

Es la segunda vez en la semana que el mismo razonamiento falla: construir una hipótesis sobre los datos sin comprobar antes si hay consumidor. La lección ya estaba escrita en A.15.4 y no se aplicó.

### A.16.4 Estado: el ciclo del contrato queda CERRADO

| | |
|---|---|
| Contrato en Fase A y F-08C, cuatro caminos | Validado |
| G1, G2, G4, nivel 1 del pool | Validado |
| Mapa de alternativas y filtro del pool | Validado |
| B1 — anclas a "ya visto" | Validado |
| **B2 — de raíz** | **Validado** |
| Fases 3.1, 3.2 y 4 (API, bloques, `% match` real) | Validado |
| Reinicio por categoría, con su UX | Validado |

### A.16.5 Pendientes

| Gap | Notas |
|---|---|
| **C1** — `outerwear` sin steering text | Sprint propio con medición. KIMONOS y CHAQUETAS tampoco tienen grupo padre |
| **Outfit y estándar sin contrato** | Devuelven lista plana; el widget pinta rejilla única. Decisión pendiente de si merece la pena |
| **E5 niveles 2 y 3** | El nivel 2 (filtro dentro de la búsqueda) retiraría el contrato implícito ACCESSORIES/JOYAS |
| **B7** — Fase A ignora el texto de la consulta | Decisión de producto |
| Asimetría joyería/complementos | Un clutch ofrece aros; unos aros ya no ofrecen clutch. A decidir con la pantalla delante |
| LFM2-24B devuelve 404 | Desde el 02/10; 100% de fallback a GPT-4o-mini |
| `REDIS MISS` perdiendo sesiones | Visto el 15/10; sin diagnosticar |
| Ruido de log en el reinicio | Cada turno posterior vuelve a registrar los productos liberados del turno pre-reinicio. Correcto pero verboso |
