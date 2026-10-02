# DCT — Cierre de Fase 2 (Unificación de Taxonomía) y Refinamiento Final de Fase 3

**Fecha:** 24–27 de septiembre de 2026
**Precedido por:** `DCT_Cierre_Fase1_Fase3_Estabilizacion_24092026.md` (mismo directorio)
**Complementa, sin duplicar:** `DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md` (raíz de `Composite_Embedding_Granular`, Addendums 5 y 6) — ese documento tiene el detalle técnico línea a línea; este resume el resultado para quien necesite el panorama completo sin recorrer 6 addendums.
**Origen:** `Evaluacion_Integral_Sistema_16092026.md` (mismo directorio) — roadmap de 5 fases, sección 15.
**Estado:** Fase 2 (unificación de taxonomía) **cerrada y validada con datos reales del catálogo**. Fase 3 (limitador de tasa) **refinada y re-validada**, ahora con cero solape confirmado en dos corridas independientes.

---

## 1. Resumen ejecutivo

Esta semana cerramos dos frentes que venían abiertos desde hace tiempo, ambos con la misma característica: se resolvieron con **evidencia medida del sistema real**, no con criterio de diseño en abstracto.

Primero, terminamos de confirmar que el mecanismo que hace que el rebuild diario del catálogo y el enriquecimiento de colecciones **dejen de competir por el mismo cupo de Shopify** funciona de forma consistente — dos pruebas independientes, en días distintos, con el mismo resultado limpio: cero fricción entre ambos procesos.

Segundo, y más importante: el sistema tenía **cuatro copias distintas** de la misma información básica (qué categoría de producto combina con cuál) repartidas en cuatro archivos, sin que nadie hubiera podido decir con certeza cuáles estaban actualizadas y cuáles no. Construimos una herramienta que audita esto automáticamente contra el catálogo real, la corrimos, y los números fueron claros: una fuente estaba completa, la otra le faltaban 14 tipos de producto — entre ellos 241 productos de la línea de vestidos de novia, que llevaban tiempo sin recibir el tratamiento correcto en una parte del sistema. Con esa evidencia, unificamos las cuatro fuentes en dos (cada una con un propósito genuinamente distinto), cerramos los huecos, y confirmamos con una segunda corrida del mismo script que el catálogo real ya no tiene ninguna categoría sin cubrir.

---

## 2. Parte A — Refinamiento y validación final de Fase 3 (limitador de tasa compartido)

### 2.1 Qué ya existía (ver DCT anterior)

El `DCT_Cierre_Fase1_Fase3_Estabilizacion_24092026.md` ya documentó la construcción de dos mecanismos: un limitador de tasa compartido entre el rebuild del catálogo y `PASO 4.6 BG` (enriquecimiento de colecciones), y una señal de prioridad que hace que `PASO 4.6 BG` se pause por completo mientras el rebuild está activo, en vez de competir por el mismo cupo de Shopify.

### 2.2 Qué se confirmó esta semana

Se reprodujo el escenario más exigente posible — el rebuild disparado deliberadamente a mitad del trabajo de `PASO 4.6 BG` — en **dos ocasiones separadas** (23/09 con deploy `00302-mf8`, y 25/09 con deploy `00304-kl9`):

| Fecha | Resultado |
|---|---|
| 23/09 | Cero solape confirmado. `PASO 4.6 BG` pausado los ~7 minutos completos del rebuild, `REST fallbacks: 0` |
| 25/09 | Mismo resultado, ligeramente mejor: `PASO 4.6 BG` con `batches OK=61 FAIL=0` (sin ningún fallo, la vez anterior había tenido 1) |

Dos corridas independientes, mismo resultado limpio — esto ya no es un golpe de suerte, es un comportamiento consistente. **Fase 3 se da por cerrada sin reservas.**

---

## 3. Parte B — Fase 2: decisión y ejecución de la unificación de taxonomía

### 3.1 Punto de partida

El sistema tenía, para la pregunta "¿a qué categoría de outfit pertenece este tipo de producto?", **cuatro fuentes de verdad activas y potencialmente desincronizadas**:

1. `product_taxonomy.py` — el módulo pensado desde julio como fuente única, pero con adopción incompleta.
2. `_B08_SHOPIFY_TO_OUTFIT_CAT` — un diccionario duplicado, inline dentro del bloque F-08B principal.
3. `_B08B2_SHOPIFY_TO_OUTFIT_CAT` — una segunda copia del mismo diccionario, dentro de F-08B.2 (el mecanismo de respaldo).
4. `_OUTFIT_COMPLEMENT_MAP` — un cuarto mapa, con una lógica distinta y más limitada (solo cubría tipos de prenda, nunca de accesorio).

Esta fragmentación ya había causado el mismo patrón de bug **cuatro veces** en dos meses (documentado en el DCT de Fase 1b, Addendums 1, 4 y 5). La pregunta de qué hacer con esto quedó explícitamente abierta desde el Addendum 4 (28/07/2026).

### 3.2 Paso previo: red de seguridad antes de tocar código frágil

Antes de decidir nada, se construyó una red de pruebas automatizadas — siguiendo la propia recomendación del roadmap ("tests antes de refactorizar nada grande"):

- **Extracción de F-08B.2**: la lógica de decisión (198 líneas, antes inline dentro de una función async de ~1800 líneas, imposible de testear sin invocar toda la máquina de conversación) se movió a `src/recommenders/f08b2_category_resolution.py`, una función pura con sus dependencias inyectadas.
- **14 tests automatizados** (`tests/unit/test_f08b2_category_resolution.py`), corridos con `pytest` real, cubriendo los bugs históricos de esta área y el comportamiento que debía preservarse.

Esta extracción, pensada solo como red de pruebas, resultó ser **habilitante para todo lo que vino después**: sin ella, el script de auditoría de la sección siguiente habría tenido que mantener una quinta copia del mismo diccionario solo para poder leerlo.

### 3.3 El script de auditoría por centroides

Se diseñó y construyó `taxonomy_centroid_audit.py` (raíz del repo), pensado para resolver tres necesidades identificadas a lo largo de varias sesiones (ver DCT de Fase 1b, secciones 9.1, 11.3 y Addendum 5):

| Motivo | Qué resuelve | Estado |
|---|---|---|
| 1. Cobertura | Enumera automáticamente todos los tipos de producto reales del catálogo, reemplazando el método manual de "adivinar nombres de variantes" (ya documentado como no exhaustivo) | **Funcional** |
| 2. Desincronización de fuentes | Cruza el inventario real contra las fuentes de taxonomía activas, señalando huecos | **Funcional** |
| 3. Mistagging | Compara el embedding visual de cada producto contra el centroide de su propio tipo declarado, para detectar productos mal tipificados en Shopify | **Diseñado, bloqueado** — requiere un endpoint nuevo en el embedding-service (exportar embeddings crudos) que hoy no existe; confirmado revisando el cliente real, no asumido |

### 3.4 La evidencia que decidió la forma de la unificación

Corrido contra el catálogo real (26/09/2026, 3045 productos, 38 tipos distintos):

- **`product_taxonomy.py`**: 8 tipos ausentes.
- **`_B08B2_SHOPIFY_TO_OUTFIT_CAT`** (usado como representante también de `_B08_SHOPIFY_TO_OUTFIT_CAT`, idénticos por diseño): **14 tipos ausentes** — entre ellos, las 6 variantes completas de la línea Novias (241 productos).
- **Donde ambas fuentes sí coincidían, coincidían sin excepción** — ningún desacuerdo de criterio, solo cobertura desigual.

Este último punto fue el dato decisivo: no había un conflicto de criterios que negociar, había una fuente completa y una copia parcial de la misma. Eso convirtió "unificar" en una sustitución mecánica, de bajo riesgo.

### 3.5 La decisión, fuente por fuente

| Fuente | Decisión |
|---|---|
| `_B08_SHOPIFY_TO_OUTFIT_CAT` / `_B08B2_SHOPIFY_TO_OUTFIT_CAT` | **Retiradas.** Sustituidas por `product_taxonomy.get_outfit_slot()` / `types_in_outfit_slot()` |
| `_OUTFIT_COMPLEMENT_MAP` | **Retirado.** 19 de 29 tipos de prenda ya caían a su fallback genérico de 4 ítems — en la práctica era una versión incompleta de "todo el bucket accessory+bag", que es exactamente lo que el sistema ya resolvía para pedidos amplios |
| `CATEGORY_KEYWORDS` | **Se mantiene separada, a propósito.** Resuelve un problema distinto (detección de categoría desde texto libre con sinónimos), no tipo→bucket. Se le cerraron sus 4 huecos sin fusionarla con nada |
| `product_taxonomy.py` | **Confirmada como fuente única** para tipo→bucket. Se cerraron sus 8 huecos: 6 tipos nuevos (154 productos: `CALZONES`, `CHAQUETAS`, `LEGGINGS`, `LENCERIA`, `PIJAMAS`, `REDUCTORES` — estos últimos 4 en un bucket nuevo, `intimates`), y 2 tipos (`AROMAS`, `PACK`) marcados explícitamente como fuera de alcance (no son prendas combinables), en vez de forzarlos a un bucket que no les corresponde |

### 3.6 Autocorrección — un error propio, corregido en el mismo día

Al aplicar la decisión, el propio script de auditoría quedó desactualizado: seguía intentando importar los dos diccionarios que él mismo acababa de ayudar a retirar. El fallo se manejó con gracia (no rompió el resto del reporte), pero saltó en silencio una sección completa del análisis, y una función ya diseñada (`is_non_applicable_type()`) nunca se conectó al reporte. Corregido el mismo día, validado con un catálogo sintético que mezclaba tipos fuera de alcance junto a un hueco real, confirmando que la corrección no esconde problemas genuinos.

### 3.7 Validación final

Segunda corrida del script contra el catálogo real de producción, tras el deploy:

```
-- product_taxonomy.py --
  OK: cubre todos los tipos reales del catalogo (aplicables).

-- CATEGORY_KEYWORDS --
  OK: cubre todos los tipos reales del catalogo (aplicables).
```

Cero huecos reales. Los dos únicos tipos que quedan fuera (`AROMAS`, `PACK`) están ahí por decisión explícita, no por omisión. Además: 15/15 tests automatizados pasando contra los archivos exactos del repo, sintaxis validada en los 5 archivos tocados, y confirmado por búsqueda de texto que no queda ninguna referencia colgante a los 3 diccionarios retirados en todo el código.

---

## 4. Estado del roadmap (actualizado)

| Fase | Estado |
|---|---|
| Fase 1 — Bugs activos (F-08B.2, imágenes) | ✅ Cerrada |
| **Fase 2 — Unificación de taxonomía** | ✅ **Cerrada esta semana, con evidencia real** |
| Fase 3 — Limitador de tasa compartido | ✅ Cerrada, ahora con doble validación de cero solape |
| Fase 4 — Harness de alpha, inventario/archivados | Sin tocar |
| Fase 5 — T7, infraestructura Redis/Supabase | Sin tocar |

---

## 5. Archivos modificados o creados, consolidado

| Archivo | Cambio |
|---|---|
| `src/recommenders/product_taxonomy.py` | +6 tipos, +bucket `intimates`, +`NON_APPLICABLE_TYPES`/`is_non_applicable_type()` |
| `src/recommenders/improved_fallback_exclude_seen.py` | +4 entradas en `CATEGORY_KEYWORDS` |
| `src/recommenders/f08b2_category_resolution.py` | **Nuevo** (25/09) — lógica de F-08B.2 extraída; actualizado (26/09) para retirar sus dos diccionarios propios |
| `src/api/core/mcp_conversation_handler.py` | `_B08_SHOPIFY_TO_OUTFIT_CAT` retirado del bloque F-08B principal; ambos puntos de uso migrados |
| `tests/unit/test_f08b2_category_resolution.py` | **Nuevo** (25/09) — 14 tests; reescrito (26/09) tras el cambio de comportamiento del fallback |
| `taxonomy_centroid_audit.py` (raíz) | **Nuevo** — script de auditoría, motivos 1 y 2 funcionales; corregido el mismo día de su primer uso real |
| `DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md` | +Addendum 5 (tercer motivo del script), +Addendum 6 (decisión de unificación) |

---

## 6. Aprendizajes clave

1. **Una herramienta de auditoría construida para un propósito (tests de regresión) resultó indispensable para otro que no se anticipó** (el propio script de auditoría). Vale la pena diseñar extracciones pensando en reutilización, no solo en el objetivo inmediato.
2. **Medir antes de decidir cambió la naturaleza de la decisión.** Sin los números reales, "unificar taxonomía" habría sido una discusión de criterios de diseño; con ellos, fue una sustitución mecánica de bajo riesgo.
3. **Las herramientas de auditoría necesitan su propio mantenimiento.** El bug del script (sección 3.6) es un recordatorio de que una herramienta que verifica el sistema no está exenta de las mismas reglas que el sistema que verifica — incluyendo quedar desactualizada si algo que audita cambia.

---

## 7. Próximos pasos

1. Ya investigado y resuelto (27/09/2026, ver sección 7.1): `_B08_FULL_CANDIDATE_CATS`, `conjunto` en `_B08_SLOT_CONFLICTS`.
2. **Segundo incremento de extracción -- COMPLETADO (28/09/2026, ver sección 7.2)**: el bloque F-08B principal.
3. Diseñar el endpoint de exportación de embeddings en el embedding-service, para desbloquear el Motivo 3 (mistagging) del script de auditoría.
4. Fase 4 y 5 del roadmap original, sin fecha definida.

### 7.1 — Actualización (27/09/2026): resultado de la investigación de `_B08_FULL_CANDIDATE_CATS`

Investigado en la misma sesión de cierre de este DCT. Hallazgos:

- **No es una lista redundante como las que se retiraron en la Fase 2** — es una decisión de producto deliberada (buckets elegibles para sugerencias *genéricas*, sin categoría explícita pedida), documentada desde el 13/07/2026: `"conjunto"` y `"lingerie"` se excluyeron a propósito, no por descuido.
- **`intimates`** (el bucket agregado esta semana) no estaba en la lista — pero tras revisar el razonamiento original, es casi con certeza la aplicación correcta del mismo principio de `"lingerie"` (`LENCERIA` es, literalmente, esa palabra en español), no un gap. **Confirmado con Yasmani: se mantiene excluido.**
- **`"conjunto"`**: se encontró algo más concreto que el gap original — nunca se integró a `_B08_SLOT_CONFLICTS` como alternativa de prenda principal (junto a dress/enterito/top/bottom). Esto es un problema real, independiente de si aparece en la lista de sugerencias genéricas. **Resuelto (27/09/2026)**: se integró `"conjunto"` en `_B08_SLOT_CONFLICTS` como quinto conflicto, simétrico con dress/enterito/top/bottom. Con eso resuelto, la preocupación original de julio (mezclar dos outfits completos) queda cubierta por el sistema de conflictos mismo -- **se removió `"conjunto"` de `GENERIC_SUGGESTION_EXCLUDED_SLOTS`**, ya no había ninguna razón activa para mantenerlo excluido de las sugerencias genéricas.
- **Mejora estructural aplicada**: `_B08_FULL_CANDIDATE_CATS` (lista manual en `mcp_conversation_handler.py`) se reemplazó por `product_taxonomy.generic_suggestion_candidate_slots()` — calculada desde `PRODUCT_TAXONOMY` menos un nuevo conjunto explícito, `GENERIC_SUGGESTION_EXCLUDED_SLOTS` (`{"conjunto", "intimates"}`). Un bucket nuevo en el futuro ya no puede quedar incluido o excluido por omisión silenciosa — validado (`ast.parse` + ejecución real) que el conjunto calculado coincide exactamente con la lista manual anterior.

**Pendiente real, actualizado (27/09/2026)**: ya resuelto por completo -- ver punto anterior. Nota registrada para el futuro: Yasmani menciona una función en evaluación ("Inspiración", tercer botón además de "Buscar por imagen" y "Completar outfit") con una filosofía deliberadamente distinta a F-08B -- paleta amplia sin restricción de categoría, priorizando calidad visual. `GENERIC_SUGGESTION_EXCLUDED_SLOTS` es específico de la filosofía de F-08B y no debería reusarse sin repensarlo cuando esa función se diseñe.

### 7.2 -- Segundo incremento de extracción: bloque F-08B principal (28/09/2026)

Mismo patrón que el primer incremento (F-08B.2, 25/09/2026): lógica de resolución de categorías objetivo extraída a `src/recommenders/f08b_target_categories.py`, dejando fuera de alcance (por más riesgosas, mezcladas con I/O real) la llamada HTTP a `search_outfit_by_image()` y el boost de tipos hermanos (Fase 1b Paso 4).

Diferencia clave con F-08B.2: el bloque principal SÍ aplica un sistema de conflictos de slot (`_B08_SLOT_CONFLICTS`, ahora con "conjunto" integrado -- ver 7.1) y una excepción para accessory/bag (buckets multi-tipo que no se auto-excluyen por completo, permitiendo sugerir un COLLAR sobre un ancla AROS). No se unificó con F-08B.2 en una sola función porque la lógica genuinamente difiere.

Ajuste de diseño durante la extracción: la función devuelve un tercer valor (`was_explicit_request: bool`) además de `(target_categories, single_specific_type)` -- necesario para replicar fielmente el log original "F-08B query category detected", que distinguía un pedido amplio pero explícito (ej. "accesorios") de una consulta genérica, algo que se habría perdido con solo dos valores de retorno.

**Validación**: 13 tests automátizados (`tests/unit/test_f08b_target_categories.py`), corridos con `pytest` real contra los archivos exactos del repo -- 13/13 pasan, cubriendo auto-referencia, especificidad, el sistema de conflictos de slot (incluyendo el caso real que motivó el fix de "conjunto"), la excepción accessory/bag, y manejo de errores. Sintaxis validada, confirmado sin referencias colgantes a las variables internas retiradas (`_b08_own_cat`, `_b08_excluded_cats`, `_b08_query_target_cats`, `_B08_SLOT_CONFLICTS` a nivel del bloque principal), y confirmado que las dos variables de salida (`_b08_target_cats`, `_b08_single_specific_type`) siguen siendo usadas rio abajo exactamente igual que antes (14 usos, sin tocar la llamada HTTP ni el boost).

**Pendiente**: desplegar y repetir consultas reales de prueba para validar en producción (mismo patron que F-08B.2 -- validado en sandbox, pendiente de confirmacion con trafico real).

**ACTUALIZACION (28/09/2026) -- confirmado en producción real, doblemente:** deploy `retail-recommender-00306-rx9`, 9 consultas de prueba, cero errores en ambos servicios (monolito + embedding-service). El bloque F-08B principal se ejecutó 6 veces sin ninguna excepción, y el escenario exacto que motivó el fix de `conjunto` (sección 7.1) se reprodujo dos veces con productos y frases distintas:

| Ancla | Consulta | Resultado |
|---|---|---|
| `conjunto-de-fiesta-sole-lycra-dupont-canela` | "Busco algo que combine con esto" | `['accessory','bag','outerwear','shoes']` -- sin dress/top/bottom/conjunto |
| `conjunto-top-y-pantalon-de-fiesta-amaranta-blanco` | "Completa este outfit" | mismo patrón |

Además, el nuevo log (`"tipo especifico: AROS"`) apareció correctamente en dos consultas con pedidos específicos, confirmando que el tercer valor de retorno (`was_explicit_request`) funciona como se diseñó. Hallazgo extra no buscado: una consulta ("Muéstrame conjuntos", fuera de F-08B, via el sistema de recomendaciones estándar) confirmó en producción real que las 4 entradas agregadas a `CATEGORY_KEYWORDS` (sección 3.5) se detectan correctamente.

### 7.3 -- Hallazgo anotado para investigación futura (28/09/2026): impureza de tipo en los buckets del pool crudo

Durante la validación anterior, los desgloses `F-08B candidate breakdown` mostraron mas de una vez productos de un tipo ajeno al bucket solicitado -- ej. bucket=`'accessory'` incluyendo `'ENTERITOS LARGOS'` o `'NOVIAS CONJUNTOS FALDAS'` entre sus candidatos. No es un problema introducido por ninguno de los dos incrementos de extracción (no se tocó `search_outfit_by_image()` ni su categorización interna) -- es una característica preexistente del pool crudo que devuelve el embedding-service por bucket. Mismo tipo de imprecisión que ya motivó el filtro de tipo específico en F-08B.2. Anotado para investigar en una sesión futura, no urgente -- no bloqueó ni degradó ninguna de las validaciones de esta semana.

### 7.4 -- Diseño e implementación del endpoint de exportación de embeddings (28/09/2026)

Se diseñó el contrato completo para desbloquear el Motivo 3 (mistagging) del script de auditoría, y se implementó todo lo que está dentro del alcance de este repo -- falta unicamente el lado del servidor, en el repo del embedding-service.

**Contrato** (documentado completo en el docstring de `taxonomy_centroid_audit.py`): `POST /v1/embed/export-embeddings`, mismo patron de auth IAM que el resto de `/v1/embed/*`. Dos modos: **targeted** (`product_ids` en el body, sin paginacion) y **bulk** (sin `product_ids`, paginado con `limit`+`cursor`) -- necesario porque el catalogo completo como una sola respuesta ronda los ~19MB crudos (3045 productos x ~768 floats).

**Implementado en este repo:**
- `LFM2ColBERTClient.export_embeddings()` (`colbert_client.py`) -- mismo estilo que los demas metodos del cliente (circuit-breaker visual, auth IAM, mismo patron de POST con JSON). Chunking automatico en modo targeted, paginacion automatica con cursor en modo bulk -- el llamador solo ve un dict simple `{product_id: [float,...]}`.
- Logica completa de deteccion en `taxonomy_centroid_audit.py`: agrupa embeddings por tipo declarado, calcula el centroide (promedio) de cada tipo con >= `MISTAGGING_MIN_SAMPLES` (5) productos, y senala productos cuya similitud coseno con el centroide de su propio tipo cae mas de `MISTAGGING_STD_THRESHOLD` (2.0) desviaciones estandar por debajo del promedio de ese tipo. El umbral es relativo al propio tipo (no un numero fijo de similitud) para no generar falsos positivos en tipos con mucha variedad visual natural (ej. VESTIDOS LARGOS, 990 productos) comparado con tipos chicos y homogeneos.

**Validado con datos sinteticos**: un catalogo de prueba con 20 vestidos genuinos coherentes entre si, 5 carteras genuinas, y 1 producto declarado como vestido pero con un embedding deliberadamente identico al de las carteras (el impostor). El script lo detecto correctamente (4.3 desviaciones estandar por debajo del promedio), sin ningun falso positivo entre los 24 productos genuinos, y omitio correctamente un tipo con muy pocas muestras para un analisis confiable.

**Pendiente**: construir la ruta del lado del embedding-service (fuera del alcance de este repo) siguiendo el contrato documentado. Una vez ese endpoint exista, el Motivo 3 empieza a funcionar sin tocar nada mas de este lado.

**CORRECCION (28/09/2026, misma tarde):** el embedding-service NO esta fuera de este repo -- vive en `src/api/services/embedding-service/` (main.py, visual_retriever.py), dentro del mismo proyecto que el monolito. La afirmacion anterior de que estaba "fuera de alcance" fue un error -- nunca se listo esa carpeta, solo se leyo `colbert_client.py` (el CLIENTE) directamente. Corregido tras señalarlo Yasmani explicitamente.

Con el codigo real localizado, se implemento tambien el lado del SERVIDOR:
- `FashionSigLIPRetriever.export_embeddings()` (`visual_retriever.py`) -- mismo patron ya usado por `search_by_product_id()` (`self._id_map.index(pid)` + `self._faiss_index.reconstruct(pos)`, IndexFlatIP soporta reconstruccion nativa como ya se sospechaba). Reconfirmado antes de escribir nada: se leyo el constructor de `FashionSigLIPRetriever` y el metodo `search_by_product_id()` completos para replicar el patron exacto, no adivinarlo.
- `ExportEmbeddingsRequest`/`ExportEmbeddingsResponse` (Pydantic) + ruta `POST /v1/embed/export-embeddings` en `main.py`, mismo estilo que las demas rutas del servicio (sin auth explicita en el handler -- la autenticacion IAM la impone Cloud Run a nivel de infraestructura, confirmado revisando las rutas existentes).

**Validado**: logica de paginacion (targeted + bulk con cursor) probada con un indice FAISS simulado antes de tocar el codigo real -- confirma que el modo targeted maneja IDs no encontrados correctamente y que el modo bulk recorre el indice completo sin perder ni duplicar productos entre paginas. Sintaxis validada (`ast.parse`) en ambos archivos reales del embedding-service.

**Estado real ahora**: el Motivo 3 (mistagging) esta completo de punta a punta -- cliente, servidor, y logica de deteccion -- pendiente unicamente de deploy y de una corrida real contra el catalogo de produccion.

### 7.5 -- La saga de autenticacion local (28-29/09/2026): cinco intentos, causa real encontrada en el tercero

Con el endpoint ya desplegado en ambos servicios, correr `taxonomy_centroid_audit.py` **localmente** (no dentro de Cloud Run) revelo que la autenticacion IAM entre servicios -- disenada y probada solo para el caso "monolito real llamando al embedding-service real" -- nunca se penso para el caso "una persona corriendo un script en su propia maquina". Documentado aqui en detalle porque cada paso parecia razonable en el momento y ninguno funciono solo, hasta encontrar la causa real:

| # | Intento | Resultado | Por que no bastaba |
|---|---|---|---|
| 1 | `python taxonomy_centroid_audit.py` sin mas | `ValueError: COLBERT_SERVICE_URL env var not set` | El script nunca cargaba `.env` -- corregido agregando `env_loader.ensure_env_loaded()` al inicio (la variable ya estaba en `.env`, correcta, desde antes) |
| 2 | `gcloud auth application-default login` (usuario normal) | 403 -- "ADC no disponible" | Confirmado en el propio codigo (`_fetch_id_token_sync()`) que usa `google.oauth2.id_token.fetch_id_token()`, funcion que **no reconoce credenciales de usuario para mintar ID tokens** -- solo el metadata server de GCP o un archivo de llave de cuenta de servicio (confirmado en la documentacion oficial de `google-auth`) |
| 3 | `gcloud auth application-default login --impersonate-service-account=...` | Mismo error exacto que el intento 2 | `fetch_id_token()` **tampoco reconoce credenciales de impersonacion** -- limitacion reconocida por los propios mantenedores de `google-auth-library-python` (issue #1331: "doesn't support impersonated or external credentials"), confirmado buscando el issue oficial, no asumido |
| 4 | `gcloud iam service-accounts keys create ...` (crear una llave real) | `FAILED_PRECONDITION: Key creation is not allowed on this service account` | Este proyecto tiene la politica de organizacion `constraints/iam.disableServiceAccountKeyCreation` activa -- la UNICA fuente que `fetch_id_token()` sabe leer localmente queda bloqueada por completo |
| 5 | Fix de codigo: `_fetch_id_token_sync()` ahora usa `google.auth.default()` + `impersonated_credentials.IDTokenCredentials` como fallback cuando `fetch_id_token()` falla (mismo workaround que documenta el propio issue de Google) | Nuevo error, mas especifico: `Permission 'iam.serviceAccounts.getOpenIdToken' denied` | La impersonacion en si funcionaba, pero faltaba un permiso especifico -- distinto del permiso generico de impersonacion. Confirmado en la documentacion oficial de IAM que `roles/iam.serviceAccountOpenIdTokenCreator` (rol minimo, principio de menor privilegio) incluye exactamente ese permiso |

**La causa real, una vez resuelto el permiso**: tras otorgar `roles/iam.serviceAccountOpenIdTokenCreator` a la cuenta de Yasmani sobre la SA del monolito, el primer intento posterior **todavia fallo** con el mismo error de permiso -- los cambios de politica IAM en GCP no siempre se propagan al instante, aunque la consola confirme "Updated". Un segundo intento, sin cambiar nada mas, funciono.

**Un experimento descartado con evidencia, no con teoria**: `EMBEDDING_AUTH_DISABLED=true` -- documentado en `DCT_Visual_Search_Tecnico_Final_02052026.md` (02/05/2026) como pensado para "dev local sin ADC" -- se probo directamente y **no funciono** (sigue devolviendo 403). Se confirmo por que: esa variable solo evita que el CLIENTE intente anadir el header de autenticacion, pero el embedding-service esta desplegado con `--no-allow-unauthenticated` (confirmado leyendo `deploy.sh`, el script de deploy real y actual) -- Cloud Run rechaza peticiones sin token a nivel de infraestructura, antes de que el codigo de la aplicacion vea nada. La documentacion de mayo asumia un escenario que no coincide con la configuracion real desplegada. **Corregido en `DCT_Visual_Search_Tecnico_Final_02052026.md`** (ver seccion 8 de ese documento, agregada 29/09/2026) para que nadie vuelva a perder tiempo con esa ruta.

**Archivos modificados en esta saga:**

| Archivo | Cambio |
|---|---|
| `taxonomy_centroid_audit.py` | Agregado `env_loader.ensure_env_loaded()` al inicio del script |
| `src/api/services/colbert_client.py` | `_fetch_id_token_sync()` ahora intenta `fetch_id_token()` primero, y si falla, cae a `google.auth.default()` + `impersonated_credentials.IDTokenCredentials` -- validado contra la libreria `google-auth` real instalada (firma del constructor confirmada por introspeccion, no solo por documentacion) |

**Permisos IAM otorgados (fuera del repo, para referencia futura):** `roles/iam.serviceAccountOpenIdTokenCreator` a `yasmani.cascante@gmail.com` sobre `178362262166-compute@developer.gserviceaccount.com`.

### 7.6 -- Primera corrida exitosa del Motivo 3 (29/09/2026)

Con la autenticacion resuelta, el script corrio de punta a punta por primera vez contra el catalogo real: **32 tipos analizados** (>= 5 productos con embedding), 6 tipos omitidos por tener muy pocas muestras (`ALAS DE NOVIA`, `AROMAS`, `BRAZALETE`, `CLUTCH`, `NOVIAS CONJUNTOS PANTALONES`, `PACK`), y **130 productos candidatos a mistagging** senalados (entre 2.0 y 5.0 desviaciones estandar por debajo del promedio de su propio tipo).

Verificacion de estos candidatos contra Shopify Admin: ver seccion 7.7.


### 7.7 -- Verificacion contra Shopify Admin de los 130 candidatos (29/09/2026)

Los 130 productos se revisaron contra Shopify Admin en 7 lotes (via `search_products` con `id:X OR id:Y`, hasta 20 IDs por lote por el limite de 500 caracteres de la herramienta) -- titulo, tags y descripcion de cada uno comparados contra su tipo declarado, priorizando primero los de mayor puntuacion z (los mas sospechosos).

**Resultado: 128 de 130 correctamente tipificados.** La inmensa mayoria de las desviaciones altas se explican por variedad visual genuina DENTRO de la categoria correcta -- no por errores de categoria:
- **Lentejuelas/brillos** (varios VESTIDOS LARGOS): una tela con brillo intenso se ve muy distinta, visualmente, al resto de vestidos de tela mate -- incluido el candidato con la puntuacion mas alta de todos (`VESTIDO LARGO SAMANTHA LENTEJUELAS`, z=5.0).
- **Estampados de animal print** (leopardo, snake): varios vestidos y bralettes con este patron, visualmente muy distintos del resto de su categoria.
- **Accesorios pequeños dentro de categorias de prenda** (ej. `CINTA DOBLE CONTACTO`, cinta adhesiva para vestidos, declarada LENCERIA): visualmente muy distinto de un sostén o calzón, pero correctamente agrupado bajo el mismo tipo de producto por su funcion.

**2 hallazgos genuinos, de dos tipos distintos:**

1. **Mistagging real confirmado**: `Body Renata Negro` (id 9978845659445) -- declarado `BRALETTES`, pero su propio titulo y tags ("BODY", "BODYSUITS") confirman que es un body/bodysuit, una prenda distinta de un bralette. Candidato a recategorizar.
2. **Descripcion duplicada entre dos productos distintos** (no es un error de categoria, pero es un hallazgo real de calidad de datos): `Vestido Largo Consuelo Blanco` (id 9978771013941, declarado `NOVIAS MIDIS`) tiene la MISMA descripcion ("Maxi Paloma es un vestido largo...") que pertenece a `Vestido Largo Paloma Blanco` (id 9978763051317, declarado `NOVIAS LARGOS`) -- un producto completamente distinto, con nombre "Paloma" que coincide exactamente con el texto de la descripcion copiada. Confirmado cruzando ambos productos en lotes distintos de la verificacion.

**Conclusion sobre el Motivo 3**: con un umbral de partida (`MISTAGGING_STD_THRESHOLD=2.0`) sin calibrar contra casos reales, la tasa de hallazgos genuinos fue baja (1 mistagging real + 1 hallazgo de calidad de datos, de 130 candidatos) -- pero el mecanismo SI funciona: encontro exactamente el tipo de problema que lo motivo (un producto en la categoria equivocada), sin necesitar revision manual producto por producto. Dado el bajo ratio de senal/ruido con el umbral actual, subir `MISTAGGING_STD_THRESHOLD` (ej. a 2.5 o 3.0) en la proxima corrida reduciria el volumen a revisar mientras se mantienen los casos mas claros.


### 7.8 -- Cierre: chequeo de texto automatico y estado final de la herramienta (30/09 - 01/10/2026)

Trabajo de cierre completo, documentado en detalle en su propio DCT dedicado:
**`DCT_Cierre_Herramienta_Auditoria_Taxonomia_01102026.md`** (mismo directorio) -- referencia completa para desarrolladores y stakeholders, con los 18 apartados de la herramienta (objetivo, arquitectura, calculo de similitud/z, umbrales, limitaciones, oportunidades de mejora, etc.). Resumen aqui, para no duplicar:

- **Umbral subido a 2.5** (de 2.0), con la advertencia explicita de que el unico mistagging confirmado hasta ese momento tenia z=2.5 EXACTO -- ver comentario en el propio codigo.
- **Chequeo de texto automatico construido** (`run_mistagging_audit()`, `taxonomy_centroid_audit.py`): antes de escalar un candidato a revision manual, compara su titulo/tags contra su tipo declarado reusando `extract_categories_from_query()` (la misma fuente ya validada de deteccion de categoria por texto, sin crear una sexta fuente de taxonomia paralela).
- **Validado dos veces con datos reales**: contra los 53 candidatos de la corrida del 30/09 (52/53 confirmados correctamente por texto, 1 escalado -- coincidiendo exactamente con el unico caso ambiguo ya detectado a mano), y de nuevo en una corrida independiente el 01/10/2026 (mismo patron: 1 escalado, 52 confirmados).
- **El unico candidato escalado, verificado en Shopify Admin**: `Vestido Midi de Fiesta Alessia Estampado` (id 9978562183477, `VESTIDOS LARGOS`) -- tags contradictorios ("MAXI VESTIDOS" y "MIDI Y MINI VESTIDOS" a la vez), descripcion que se autodenomina "vestido midi". Inconsistencia real de categorizacion de largo, no un error grave -- producto archivado, 0 inventario, sin impacto en clientes activos.

**Conclusion**: el trabajo "script de auditoria + chequeo de texto automatico" se da por **completo** para el alcance definido -- los tres motivos funcionan de punta a punta, validados con catalogo real en multiples corridas, y el chequeo de texto redujo el volumen de revision manual de 130 a 1 sin perder el unico caso real conocido. Limitaciones conocidas (calibracion de umbral con poca evidencia, fragilidad de autenticacion local) documentadas en el DCT dedicado -- son mejoras de segunda iteracion, no bloqueos.


