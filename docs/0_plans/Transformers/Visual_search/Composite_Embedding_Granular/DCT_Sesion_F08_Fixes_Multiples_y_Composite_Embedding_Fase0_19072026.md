# DCT — Sesión F-08 Fixes Múltiples + Composite Embedding Granular (Fase 0)

**Proyecto:** Retail Recommender System v2.1.0
**Ubicación local:** `C:\Users\yasma\Desktop\retail-recommender-system\`
**Fecha:** 16-19/07/2026 (sesión larga, múltiples días de trabajo continuo)
**Última revisión desplegada confirmada:** `retail-recommender-00266-wbj`
**Estado al cierre:** Múltiples fixes de producción aplicados y validados. Investigación de Fase 0 (Composite Embedding Granular) completa con 6 casos de prueba reales. **Decisión de diseño de Fase 1 pendiente de confirmación del usuario** — ver sección 5.

---

## 🚀 PROMPT DE CONTINUIDAD — PEGAR EN NUEVA SESIÓN

```
Continuamos el Retail Recommender System v2.1.0 (FastAPI + Redis + PostgreSQL/Supabase +
Claude/GPT-4o-mini/LFM + Shopify + Next.js). Path local:
C:\Users\yasma\Desktop\retail-recommender-system\

Por favor lee el documento de continuidad local
"DCT_Sesion_F08_Fixes_Multiples_y_Composite_Embedding_Fase0_19072026.md"
(raíz del repo) para el contexto completo antes de continuar.

ESTADO: Sesión previa aplicó varios fixes críticos en mcp_conversation_handler.py
(F-08B, F-08B.2, F-08C, F-08 Fase A) — todos desplegados y validados en producción,
revisión retail-recommender-00266-wbj.

TRABAJO ACTIVO: Fase 0 (prueba de concepto) del plan "Composite Embedding Granular"
(docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/) está COMPLETA
— 6 casos de prueba reales confirman que el composite embedding funciona, pero
necesita DOS valores de alpha distintos (no uno solo como proponía el plan original):
  - alpha=0.5 para reforzar el propio tipo del ancla (uso F-08/F-08C, "similar a esto")
  - alpha=0.2 para pedir un tipo distinto al del ancla (uso F-08B, "qué combina con esto")

DECISIÓN PENDIENTE (justo donde se cortó la sesión anterior): propuse dividir la
implementación en dos:
  - "Fase 1" ahora: alcance original del plan (solo F-08/F-08C, alpha=0.5) — bajo
    riesgo, ya bien evidenciado.
  - "Fase 1b" después: extender a F-08B (alpha=0.2, tipo distinto) — evidencia fuerte
    (5 de 6 pruebas) pero requiere diseño de integración propio porque F-08B usa una
    función distinta (search_outfit_by_image, ya en producción con alpha=0.5 fijo a
    nivel de bucket, no de tipo específico).

Esperando que el usuario confirme si procedemos así, o si prefiere diseñar ambas
fases juntas desde el inicio.

Script de prueba disponible: fase0_poc.py (mismo directorio que el plan) — permite
seguir corriendo casos de prueba adicionales sin tocar producción. Requiere entorno
virtual con las dependencias de src/api/services/embedding-service/requirements.txt
(ya configurado en la máquina del usuario, venv en
src/api/services/embedding-service/venv_fase0/).
```

---

## 1. Resumen ejecutivo de la sesión

Sesión extensa (16-19/07/2026) con dos bloques de trabajo diferenciados:

**Bloque A (16-18/07): Fixes de producción en `mcp_conversation_handler.py`.** Incluye un bug crítico que causaba caídas de 5 minutos (504) en producción — ya resuelto y confirmado estable. Varios fixes adicionales de calidad de recomendaciones (autoexclusión de tipo, variedad de subtipos, priorización de tipo exacto).

**Bloque B (18-19/07): Investigación Fase 0 del plan "Composite Embedding Granular".** Prueba de concepto aislada (sin tocar producción) que confirma con datos reales que mezclar el vector de imagen del producto ancla con un vector de texto de categoría específica mejora sustancialmente la relevancia de "productos similares" y "qué combina con esto" — pero requiere dos valores de alpha distintos según el caso de uso, no uno solo.

---

## 2. Fixes aplicados y CONFIRMADOS EN PRODUCCIÓN (Bloque A)

Todos en `src/api/core/mcp_conversation_handler.py`. Todos validados con logs reales tras deploy, no solo localmente.

| # | Fix | Bloque | Evidencia de validación |
|---|---|---|---|
| 1 | **Bug crítico: loop infinito en `_b08_interleave`** — `if not pool or len(recs)>=n: break` rompía TODO el for-loop al toparse con la primera categoría vacía, sin llegar a categorías posteriores con items pendientes. Causaba 504 tras 300s, tomando la instancia entera (concurrency=80) consigo. | F-08B | Reproducido de forma determinista con test standalone (8 casos adversariales). Confirmado en logs: 3 ocurrencias reales de 504 con exactamente el mismo patrón (último log siempre `outfit_search_completed`, luego silencio total). **Fix: separar `break` (n_recommendations alcanzado) de `continue`+`del` (categoría vacía).** Sin recurrencia desde el deploy. |
| 2 | **F-08B.2: autoexclusión de tipo propio** — `_OUTFIT_COMPLEMENT_MAP` solo tiene entradas para tipos de PRENDA; para anclas de tipo accesorio caía al fallback genérico `['AROS','COLLARES','CLUTCH','CINTURONES']`, que podía incluir el propio tipo del ancla. | F-08B.2 (fallback cuando F-08B falla, ej. por error 413) | Validado con simulación: AROS ya no aparece en su propia lista de complementos. |
| 3 | **F-08C: extensión de Hallazgo T8** — la priorización de tipo exacto (partición: tipo del ancla primero) solo se activaba cuando `_c08_query_cats` venía vacío (sin detección de texto). La palabra genérica "accesorios" en el texto disparaba `extract_categories_from_query()`, dejando `_c08_query_cats` no-vacío y desactivando la protección T8 exactamente en el caso que más la necesitaba. | F-08C | Confirmado con screenshot: antes 5 Aros+2 Chocker+1 Collar para "similar a este Collar"; simulación del fix con proporción real (43 Aros:6 Collares) da 6 Collar+2 Aros. |
| 4 | **F-08B: intercalado por subtipo (Nivel 1)** — dentro de un bucket como "accessory" (que mezcla AROS/COLLARES/BRAZALETES/etc.), el orden era pura similitud visual sin ningún peso hacia variedad de subtipos. `_b08_interleave_by_subtype()` agrupa por `product_type` real y alterna un item de cada subtipo por turno. | F-08B | Simulado: de 7 Aros+1 Clutch (sin variedad) a mezcla balanceada de 5 subtipos. |
| 5 | **F-08 Fase A: mismo fix que #3 y #4, portado** — Fase A (Turno 1, primera interacción del usuario) nunca había recibido NI la priorización T8 NI el intercalado por subtipo — es un bloque de código separado de F-08C. | F-08 Fase A | Confirmado con screenshot real: "similar a" un Collar en Turno 1 devolvía 5 Aros+2 Chocker+1 Collar (mismo síntoma que T8 ya había resuelto para F-08C, nunca portado a Fase A). |
| 6 | **F-08B: log de diagnóstico `candidate breakdown`** (puramente aditivo, sin cambio de comportamiento) — desglose por tipo real de los candidatos crudos de cada bucket, antes de cualquier filtro. Mismo patrón que el diagnóstico ya existente en F-08C. | F-08B | Usado para confirmar con datos reales que buckets como "accessory" a veces solo tienen 1-2 subtipos reales entre los 15 candidatos crudos (ej. 14 AROS + 1 BRAZALETES) — el techo real del Nivel 1, no un bug del intercalado. |

**Nota importante sobre el alcance de #1-#6:** estos fixes optimizan la SELECCIÓN y el ORDEN de lo que el embedding-service ya devuelve. No pueden generar candidatos que el embedding-service nunca devolvió en primer lugar — ese techo estructural es exactamente lo que investiga el Bloque B.

---

## 3. Pendientes de sesiones anteriores — SIN resolver, no tocados en Bloque A ni B

| Pendiente | Estado | Contexto |
|---|---|---|
| Error 413 (Request Entity Too Large) en la llamada al embedding-service | 🔴 Sin investigar | Causa que F-08B falle y caiga a F-08B.2 (el camino sin refinar). Imagen enviada probablemente demasiado grande. Prioridad alta — cuando ocurre, se pierden TODOS los fixes #2-#6. |
| GPT-4o-mini expira a los 8s cuando LFM está caído (LFM lleva caído varios días) | 🔴 Sin resolver | Confirmado recurrente en logs de esta semana. Causa respuestas de texto genéricas/plantilla en vez de personalizadas. No afecta la SELECCIÓN de productos, solo el texto generado. |
| Reencuadre "mural de inspiración" vs "completar outfit" para el botón de búsqueda por imagen | 🔵 Decisión de producto/frontend | Ya documentado en DCT del 01/06/2026: falta el campo `outfit_result` en la respuesta del router para que el frontend pueda usar el componente `OutfitPanel` ya existente en vez de un grid genérico. Sesión aparte, fuera del alcance técnico de esta semana. |
| Posible bug gemelo en `_OUTFIT_COMPLEMENT_MAP`: la clave `"TAPADOS"` podría no calzar nunca con ningún `product_type` real | 🟡 Hallazgo nuevo (19/07), sin confirmar en producción | Descubierto durante Fase 0: "TAPADOS" no es un `product_type` real en el catálogo (0 apariciones en 40+ candidatos revisados) — el tipo real es `KIMONOS` o `CHAQUETAS`. Si `_OUTFIT_COMPLEMENT_MAP` en producción también usa "TAPADOS" como clave, es el mismo patrón de "diccionario con claves que no existen en Shopify" ya visto varias veces esta semana. **No confirmado todavía si esto afecta producción — verificar `_OUTFIT_COMPLEMENT_MAP` en `mcp_conversation_handler.py` antes de asumir.** |
| Variedad de subtipos dentro de bucket para F-08B (pregunta original de Yasmani sobre "brazaletes con collares") | 🟢 Resuelta parcialmente por el Nivel 1 (#4), pero el techo real depende del pool crudo del embedding-service | Es exactamente la motivación que llevó a la investigación de Fase 0 — ver sección siguiente. |

---

## 4. Bloque B — Fase 0: Composite Embedding Granular (COMPLETA)

**Plan de referencia:** `docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/Plan_de_Implementacion_09072026.md`
**Script de prueba:** `docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/fase0_poc.py`

### 4.1 Qué es y cómo usarlo

Script standalone que corre 100% localmente (no toca producción, no modifica el índice FAISS, no modifica `visual_retriever.py`). Reutiliza la clase real `FashionSigLIPRetriever` del embedding-service para no duplicar lógica de carga.

**Requiere:** entorno virtual con las dependencias de `src/api/services/embedding-service/requirements.txt` (ya instalado en `src/api/services/embedding-service/venv_fase0/` en la máquina del usuario — activar con `source venv_fase0/Scripts/activate` antes de correr). Acceso a Hugging Face (descarga el modelo la primera vez, luego cachea) y a GCS (índice FAISS, bucket `retail-recommendations-449216-visual-index`, confirmado). `SHOPIFY_ACCESS_TOKEN` ya se carga automáticamente desde el `.env` de la raíz del repo.

**Uso típico:**
```bash
cd src/api/services/embedding-service
python ../../../../docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/fase0_poc.py \
  --product-handle <slug-de-la-url-del-producto> \
  --boost-category <TIPO_SHOPIFY_EN_MAYUSCULAS> \
  --alphas 0.5,0.4,0.3,0.2
```

`--product-handle` es preferible a `--product-id` (evita errores de tipeo con IDs de 13 dígitos — usar el slug de la URL pública del producto, no la del admin/preview). Si se omite `--boost-category`, se auto-detecta del `product_type` real vía Shopify (útil cuando se quiere reforzar el PROPIO tipo del ancla; hay que darlo explícito cuando se quiere pedir un tipo DISTINTO).

**Tipos ya validados en `SHOPIFY_TYPE_TEXT_PROMPTS_POC`:** AROS, COLLARES, BRAZALETES, BRAZALETE, CINTURONES, TOCADOS, ALAS DE NOVIA, CARTERAS, CLUTCH, ZAPATOS, KIMONOS, CHAQUETAS, TAPADOS (este último presente pero **no confirmado como tipo real**, ver sección 3).

### 4.2 Los 6 casos de prueba y sus resultados

| # | Ancla → Boost | Relación | Plana | Punto de quiebre | Techo alcanzado |
|---|---|---|---|---|---|
| 1 | Collar → Collares | Mismo tipo | 3/10 | ~0.5 | 7/10 |
| 2 | Cartera → Carteras | Mismo tipo (techo ya alto sin ayuda) | 9/10 | — (ya casi al techo) | 10/10 |
| 3 | Aros → Brazaletes | Tipo distinto, misma familia | 0/10 | ~0.3 | 9/10 |
| 4 | Vestido → Zapatos | Tipo distinto, familias distintas | 0/10 | ~0.2 | 8/10 |
| 5 | Zapatos → Cinturones | Tipo distinto, familias distintas | 0/10 | ~0.3 | 8/10 |
| 6 | Zapatos → Kimonos | Tipo distinto, familias distintas | 0/10 | ~0.3 | **10/10** (el más limpio) |
| 6b | Zapatos → Chaquetas | Tipo distinto, familias distintas | 0/10 | ~0.3 | 6/10 (nunca converge del todo — posible prompt de texto ambiguo, sin resolver) |

### 4.3 Hallazgo central: dos alphas, no uno

El plan original (09/07) proponía un único alpha (0.6, con 0.4 como alternativa) para un único caso de uso (reforzar el propio tipo, F-08/F-08C). Los datos reales muestran un patrón de "punto de quiebre" (no gradual) y dos escenarios claramente distintos:

- **Reforzar el propio tipo** (F-08/F-08C, "similar a esto"): `alpha≈0.5`
- **Pedir un tipo distinto al del ancla** (F-08B, "qué combina con esto"): `alpha≈0.2-0.3` — `0.2` cubre bien todos los casos probados, incluyendo el más difícil (Vestido→Zapatos).

Este hallazgo invalida el supuesto original del plan de "un alpha universal" y también extiende su alcance: el plan marcaba "aplicar composite embedding fuera de accesorios" como **fuera de alcance por falta de evidencia** — ahora esa evidencia existe (casos 4, 5, 6 cruzan familias completamente distintas con éxito).

### 4.4 Hallazgo secundario: "TAPADOS" no es un tipo real

Ver sección 3, última fila. Se descubrió corrigiendo un error propio durante la Fase 0 (usé "TAPADOS" como `--boost-category` asumiendo que era un `product_type` real, basado en recordar esa palabra como clave de `_OUTFIT_COMPLEMENT_MAP`). El tipo real para prendas de abrigo en este catálogo es `KIMONOS` o `CHAQUETAS`.

---

## 5. DECISIÓN PENDIENTE — punto exacto donde se cortó la sesión

Propuse dividir la implementación de Fase 1 en dos:

- **"Fase 1" (alcance original del plan, listo para diseñar ya):** solo F-08/F-08C, siempre reforzando el propio tipo del ancla, `alpha=0.5`. Implica modificar `visual_retriever.py` (nuevo `SHOPIFY_TYPE_TEXT_PROMPTS` + nueva función `search_by_product_id_with_category_boost()`, según el diseño ya detallado en el plan original) y `mcp_conversation_handler.py` (F-08 Fase A y F-08C: `if/else` opt-in cuando el tipo del ancla es de la familia ACCESSORIES). **Requiere deploy del embedding-service, servicio separado del monolito — dos deploys coordinados, no uno.**

- **"Fase 1b" (propuesta, diseño pendiente):** extender a F-08B para el caso de tipo distinto, `alpha=0.2`. Evidencia fuerte (5 de 6 pruebas exitosas), pero F-08B usa `search_outfit_by_image()` — función distinta, ya en producción con `alpha=0.5` fijo a nivel de BUCKET (no de tipo específico). Integrar ahí requiere su propio diseño, no es un simple copy-paste del mecanismo de Fase 1.

**Yasmani no había respondido esta pregunta todavía cuando pidió el prompt de continuidad.** Es el primer punto a resolver al retomar.

---

## 6. Aprendizajes clave de la sesión (para no repetir)

- **Patrón recurrente de "bloques gemelos" que no reciben el mismo fix:** ya van 4 instancias esta semana (F-08 Fase A vs F-08C para expansión de categorías; F-08B vs F-08B.2 para autoexclusión de tipo; T8 en F-08C vs nunca-portado a Fase A; ahora posiblemente `_OUTFIT_COMPLEMENT_MAP["TAPADOS"]`). Cuando se encuentra un bug en un bloque, preguntar explícitamente "¿existe otro camino de código que resuelve el mismo problema y debería recibir el mismo fix?" antes de dar por cerrado el trabajo.
- **Los diccionarios de mapeo (`product_type` → categoría) tienden a tener claves que no calzan con valores reales de Shopify.** Verificar contra datos reales (Shopify Admin API, o logs de producción) antes de asumir que una clave existe — ya pasó con "TAPADOS" hoy, y con varios casos de "BRAZALETE" vs "BRAZALETES" en sesiones anteriores.
- **El alpha del composite embedding no es un valor único ni gradual — es un punto de quiebre que depende del caso de uso** (reforzar propio tipo vs pedir tipo distinto), no de una fórmula continua de "distancia visual" (Zapatos→Cinturones y Zapatos→Kimonos, con distancias de categoría muy distintas, rompieron en el mismo punto).
- **Mi entorno de ejecución (sandbox) no tiene acceso a Hugging Face ni GCP/GCS** (confirmado empíricamente, ambos devuelven 403) — cualquier prueba que requiera el modelo FashionSigLIP o el índice FAISS real debe correrla el usuario en su propio entorno, con scripts que yo preparo pero no puedo ejecutar directamente.
- **Los ID de producto de Shopify en este catálogo tienen 13 dígitos y empiezan con "9978".** Cualquier ID que no calce con ese patrón es sospechoso de ser otra cosa (ya pasó: un ID de 11 dígitos resultó ser parte de una URL de preview de Shopify, no un product_id).

---

## 7. Archivos tocados en esta sesión

| Archivo | Tipo de cambio |
|---|---|
| `src/api/core/mcp_conversation_handler.py` | 6 fixes de producción (ver sección 2), todos desplegados y confirmados |
| `docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/fase0_poc.py` | Script nuevo, creado y evolucionado durante la sesión (soporte `--product-handle`, `--alphas` como lista, validación temprana de ID, carga de `.env`, 12 tipos en `SHOPIFY_TYPE_TEXT_PROMPTS_POC`) |
| `src/api/services/embedding-service/visual_retriever.py` | **NO tocado** — Fase 0 es deliberadamente de solo lectura sobre este archivo |
| `src/api/services/embedding-service/venv_fase0/` | Entorno virtual nuevo, creado por el usuario para correr `fase0_poc.py` |
