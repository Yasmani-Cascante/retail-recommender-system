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
