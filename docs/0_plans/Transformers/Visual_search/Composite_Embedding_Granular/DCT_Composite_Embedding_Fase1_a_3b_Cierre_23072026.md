
# DCT — Composite Embedding Granular (Fase 1 → Fase 3b): Cierre

**Fecha de cierre:** 23/07/2026
**Sesión previa local (Fase 0 / decisión de alcance):** DCT_Sesion_F08_Fixes_Multiples_y_Composite_Embedding_Fase0_19072026.md
**Documentos Notion revisados antes de escribir este DCT** (contexto obligatorio, ver sección 6):
- "DCT — Propagación Fix F-08C → F-08 Fase A (Category Expansion Turn 1) — 03/07/2026" (extendido hasta 11/07) — origen de "Gap C"
- "DCT — Opción A: Startup Probe HTTP + UX Cold-Start — Cierre 30/06/2026" — origen del startup probe del monolito
- "DCT — Coherencia Categórica Estricta (strict_category) — Sprint F-08C, 18/06 a 26/06/2026"
**Revisiones desplegadas:** `retail-embedding-service-00047-flj` (Fase 1), `retail-recommender-00267-glq` (Fase 3), `retail-recommender-00268-fvr` (Fase 3b)

---

## 1. Resumen ejecutivo

El plan **Composite Embedding Granular** (reforzar el propio tipo del ancla en F-08/F-08C cuando pertenece a la familia ACCESSORIES, usando `alpha=0.5` para combinar vector de imagen + vector de texto de categoría) quedó **implementado, desplegado y validado en producción con evidencia de logs reales**.

El camino tuvo un incidente serio a mitad de camino — un gap de diseño mío que dejó el código de Fase 3 inalcanzable durante ~3 días de pruebas — diagnosticado con evidencia de log y corregido en Fase 3b. Ver sección 2.

Al validar, se confirmó con datos reales el "Gap C" ya documentado el 03/07/2026 en Notion (F-08B sin granularidad de tipo específico) — la Fase 1b, ya identificada como pendiente antes de esta sesión, es la solución directa. Ver sección 5.

---

## 2. Cronología

### Fase 0 (18-19/07/2026) — POC
6 casos de prueba reales confirmaron que el composite embedding funciona, pero se necesitan dos alphas distintos según el caso de uso:
- `alpha≈0.5` para reforzar el propio tipo del ancla (uso F-08/F-08C)
- `alpha≈0.2` para pedir un tipo distinto (uso F-08B) — **Fase 1b, ver sección 5.2**

Decisión al retomar (19/07): implementar Fase 1 con interfaz parametrizada (`alpha` como parámetro explícito desde el diseño), pero desplegar solo el alcance F-08/F-08C.

### Fase 1 (19/07/2026) — `visual_retriever.py` (embedding-service)
- Nuevo dict `SHOPIFY_TYPE_TEXT_PROMPTS` (9 tipos, verificado 1:1 contra `get_parent_categories()["ACCESSORIES"]` en `improved_fallback_exclude_seen.py`)
- `warmup()` extendido para pre-cachear los 9 prompts nuevos en el mismo `self._text_embed_cache`
- Nueva función `search_by_product_id_with_category_boost(product_id, boost_category, alpha=0.5, top_k=8)`
- Desplegado y validado: `text_embed_cache: 18 categories pre-computed` confirmado en 2 cold starts de la revisión `00047-flj`, sin errores, sin overhead perceptible (warmup 3.45-4.18s, dominado por la carga del modelo de 18-25s)

### Fase 3 (19/07/2026) — integración en `mcp_conversation_handler.py`
Opt-in aditivo en F-08 Fase A (~línea 2400) y F-08C (~línea 1715): si el tipo del ancla pertenece a la familia ACCESSORIES, llama a la función de boost con `alpha=0.5` explícito; si no, sigue el camino original sin cambios. Lógica T8 (prioridad de tipo, documentada en Notion 03/07) y expansión a hermanas quedaron intactas, sin tocar.

**Incidente:** al probar en producción (20/07/2026, 7 consultas), las 4 consultas de similitud sobre accesorios fallaban con:
```
'LFM2ColBERTClient' object has no attribute 'search_by_product_id_with_category_boost'
```
**Causa raíz:** `visual_retriever.py` vive en el embedding-service (microservicio separado); el monolito solo le habla vía `LFM2ColBERTClient` (HTTP). Fase 1 agregó la función solo en el lado del embedding-service; Fase 3 hizo que el monolito la llamara — pero nunca se agregó el endpoint HTTP correspondiente ni el método cliente que lo consume. El error, capturado por un `except Exception` preexistente y amplio (diseñado para resiliencia), degradaba silenciosamente: F-08 Fase A caía a TF-IDF genérico; F-08C caía al fallback de diversificación (el mismo mecanismo de expansión a hermanas documentado el 03/07), produciendo resultados de "similitud" que en realidad mostraban un mix de tipos — indistinguibles de un completamiento de outfit (de ahí que el LLM describiera los resultados usando lenguaje de "complementar").

### Fase 3b (22/07/2026) — cerrar el círculo
Dos piezas simétricas:
- **`main.py`** (embedding-service): nuevo endpoint `GET /v1/embed/search-by-id-with-boost`, mismo patrón que `/v1/embed/search-by-id`
- **`colbert_client.py`** (monolito): nuevo método `search_by_product_id_with_category_boost()`, mismo patrón que `search_by_product_id()` (circuit breaker, auth, `_handle_visual_failure`)

`mcp_conversation_handler.py` no requirió cambios adicionales — ya llamaba al método correcto.

Desplegado ambos servicios. Validado con 7 consultas de prueba (23/07/2026) — ver sección 3.

---

## 3. Validación final (23/07/2026, revisión `00268-fvr`)

7 consultas de prueba. Las 3 de similitud (T2/T4/T6) activaron el boost correctamente, cero errores:

| Turn | Ancla (tipo) | `F-08C candidate breakdown` (pool FAISS, 50 candidatos) | % mismo tipo |
|---|---|---|---|
| T2 | AROS | `{'AROS': 50}` | 100% |
| T4 | CARTERAS | `{'CARTERAS': 46, 'AROS': 3, 'BRAZALETES': 1}` | 92% |
| T6 | COLLARES | `{'COLLARES': 15, 'AROS': 26, 'BRAZALETES': 7}` | 31% |

**Composite Embedding Granular (F-08/F-08C, alpha=0.5) — CERRADO Y VALIDADO.**

### Archivos modificados (estado final)

| Archivo | Servicio | Cambio |
|---|---|---|
| `src/api/services/embedding-service/visual_retriever.py` | embedding-service | `SHOPIFY_TYPE_TEXT_PROMPTS`, `warmup()` extendido, `search_by_product_id_with_category_boost()` |
| `src/api/services/embedding-service/main.py` | embedding-service | Endpoint `GET /v1/embed/search-by-id-with-boost` |
| `src/api/core/mcp_conversation_handler.py` | monolito | Opt-in en F-08 Fase A y F-08C (familia ACCESSORIES -> `alpha=0.5`) |
| `src/api/services/colbert_client.py` | monolito | Método `search_by_product_id_with_category_boost()` |

Todos los cambios son **aditivos** — ninguna línea preexistente fue eliminada o reescrita.

---

## 4. Efectividad de `alpha=0.5` varía por tipo (dato, no bug)

COLLARES (31% mismo tipo en el pool) es notablemente más débil que AROS (100%) o CARTERAS (92%). Consistente con el propio hallazgo de Fase 0, que ya había marcado Collar->Collares como el "punto de quiebre" de alpha=0.5. Con n=1 muestra por tipo no alcanza para decidir nada — candidato a revisar con más datos en una sesión futura. Posible dirección: alpha por tipo en vez de global.

---

## 5. Hallazgos conectados con el backlog ya existente en Notion

### 5.1 — Startup lento del monolito + Redis lento (22/07/2026, ventana de deploy)
2 intentos de arranque fallidos (`STARTUP HTTP probe failed 11 times`) antes de un 3er intento exitoso. **No es un mecanismo nuevo**: el startup probe HTTP del monolito (`/health/startup-probe`, gateado en `startup_complete and llm_warmup_complete`) existe desde el 30/06/2026 (revisión `00240-7rz`, budget `15+20×15=315s`), diseñado exactamente para rechazar tráfico a instancias no listas — funcionó como se diseñó. El diff de Fase 3b no agrega imports ni dependencias nuevas — sin indicio de que el código lo haya causado.

Dos señales adyacentes ayudan a explicar la ventana lenta:
- **LFM caído en OpenRouter (404, "No endpoints found")**: confirmado como incidente **externo y persistente desde el 10/07/2026** (documentado extensamente en Notion, con keep-alive dedicado ya implementado el 11/07 como mitigación parcial). No es nuevo.
- **Redis respondiendo con latencias de 21-39 segundos** (umbral: 1000ms): esto **sí es nuevo** — las sesiones previas solo documentan blips de Redis de ~1-1.1s, autorrecuperados. Vale la pena vigilar si se repite en el próximo deploy; no afectó las 7 pruebas (todas posteriores a la estabilización, 19:05:36 en adelante).

### 5.2 — Contaminación de mismo-tipo en buckets de F-08B ("combinar") — confirma "Gap C" (03/07/2026)

| Turn | Ancla (tipo) | Bucket propio ("accessory" o "bag") | Resultado final |
|---|---|---|---|
| T3 | AROS | `accessory: {'AROS': 15}` (100% mismo tipo, 0 útiles) | **1 producto** (único candidato del bucket "bag") |
| T5 | CARTERAS | `bag: {'CARTERAS': 15}` (100% mismo tipo) | 8 productos (bucket "accessory" compensó) |
| T7 | COLLARES | `accessory: {'COLLARES': 7, 'AROS': 8}` (mezclado) | 8 productos |

El Notion del 03/07 ya documentó la causa raíz exacta bajo el nombre **"Gap C"**: `search_outfit_by_image()` usa un solo prompt de texto genérico por bucket de outfit-category (`CATEGORY_TEXT_PROMPTS["accessory"]` mezcla aros/collares/brazaletes/cinturones/tocados en una sola frase) — sin forma de pedir "aros específicamente" al Composite Embedding, solo "accesorios en general". Esto es indistinguible de lo que observamos hoy: el bucket recupera candidatos genéricos de "accessory", que pueden (y con frecuencia lo hacen) ser del mismo tipo que el ancla, dejando la exclusión posterior con muy pocos candidatos reales — en el caso extremo de T3, cero.

**Esta sesión no descubre un gap nuevo — cuantifica con evidencia real un gap ya identificado**, y es exactamente la justificación de **Fase 1b** (extender el Composite Embedding a F-08B con `alpha=0.2` para pedir un tipo *distinto* al del ancla, interfaz ya parametrizada y lista desde Fase 1).

---

## 6. Aprendizajes clave de esta sesión

1. **Cruzar el límite monolito<->microservicio es una pieza de trabajo en 3 partes, no 2**: función en el servicio + endpoint HTTP + método cliente. Agregar solo la función y el call site dejó el código sintácticamente perfecto pero inalcanzable en runtime — ningún `py_compile` lo iba a detectar, porque el error solo existe en tiempo de ejecución, cruzando un proceso.
2. **Un smoke-test real (una llamada de prueba end-to-end) después de cruzar un límite de servicio es obligatorio** — la validación de sintaxis y estructura en cada archivo por separado no es suficiente cuando hay una llamada HTTP entre medio.
3. **Los `except Exception` amplios para resiliencia tienen un costo**: enmascaran completamente errores de integración como este. Sin los logs detallados compartidos, este bug podría haber pasado desapercibido indefinidamente (nunca generó un 500, nunca un `ERROR`, solo un `warning`).
4. **Revisar el backlog documentado antes de reportar un "hallazgo nuevo" evita duplicar diagnóstico**: lo que parecía un problema nuevo de F-08B (sección 5.2) resultó ser la confirmación cuantificada de "Gap C", ya identificado y ya con plan de solución (Fase 1b) desde el 03/07. Repasar los DCTs recientes en Notion antes de cerrar sesión es lo que permitió hacer esa conexión en vez de abrir una investigación paralela redundante.

---

## 7. Próximos pasos (para la siguiente sesión)

1. **Fase 1b**: extender Composite Embedding a F-08B con `alpha=0.2` (tipo distinto al ancla) — resuelve directamente 5.2 ("Gap C"). Interfaz ya parametrizada, requiere diseño de integración propio (`search_outfit_by_image()` aplica alpha a nivel de bucket completo hoy, no de tipo específico).
2. Evaluar alpha por tipo en vez de global para F-08/F-08C, con más datos (sección 4).
3. Monitorear startup/Redis en el próximo deploy (sección 5.1).
4. Backlog ya documentado en Notion, sin relación con esta sesión: gap ZAPATOS/CONJUNTOS en `_B08_SHOPIFY_TO_OUTFIT_CAT`, Problema 3 (asyncpg idle connections en Supabase), Artifact Registry lifecycle policy, Secret Manager audit.

---

## 8. Notion

Este DCT se mantiene local por ahora. Pendiente de decisión: crear página nueva en Notion, o añadir como sección nueva a la página "DCT — Propagación Fix F-08C → F-08 Fase A (Category Expansion Turn 1) — 03/07/2026" (que ya venía siendo extendida sesión tras sesión con hallazgos de esta misma línea de trabajo, incluyendo el propio origen de "Gap C").
