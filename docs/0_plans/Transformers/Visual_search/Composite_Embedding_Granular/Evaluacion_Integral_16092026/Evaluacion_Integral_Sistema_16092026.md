# Evaluación Integral del Sistema de Recomendaciones — Retail Recommender Platform

**Fecha:** 16/09/2026
**Rol asumido:** Principal Software Architect / AI Systems Architect / CTO técnico
**Alcance temporal reconstruido:** 30/06/2026 → 16/09/2026 (documentación local + historial de esta sesión)
**Documentos revisados en profundidad:** `Plan_de_Implementacion_09072026.md`, `PLAN_Fase1b_Revision_Arquitectonica_23072026.md`, `DCT_Composite_Embedding_Fase1_a_3b_Cierre_23072026.md`, `DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md` (con sus 4 addendums), `DCT — Propagación Fix F-08C → F-08 Fase A` (histórico Notion, 03/07 a 23/07)

---

## 1. Executive Summary

El sistema ha pasado, en cerca de tres meses de trabajo documentado, de un motor de recomendaciones con un problema de calidad conocido pero no resuelto ("resultados de similitud dominados por categorías ajenas") a un sistema con **mecanismos de corrección específicos, verificados con evidencia de producción, para las tres familias de consulta principales** (similitud F-08/F-08C, completar outfit F-08B, primer turno F-08 Fase A). Ese es un logro real y no trivial.

Al mismo tiempo, la investigación de esta sesión — y su cruce con el historial — revela un **patrón arquitectónico recurrente y no resuelto**: el sistema tiende a resolver un problema en un bloque de código y dejar un bloque "gemelo" (que atiende el mismo tipo de caso en un contexto distinto: primer turno vs. turnos siguientes, camino principal vs. fallback) sin el mismo fix, durante semanas o meses, hasta que una prueba específica lo expone. Esto ha ocurrido al menos **tres veces documentadas** (F-08 Fase A vs. F-08C en julio; F-08B vs. F-08B.2 en julio-agosto), y es indicativo de una causa de fondo: la ausencia de una fuente única de comportamiento para "¿qué categoría debería mostrarse dado este ancla y esta consulta?" — la lógica vive repartida en múltiples bloques con lógica paralela, no en una función/política compartida.

Un segundo hallazgo estructural, más grave en potencial de impacto silencioso: el catálogo que alimenta las recomendaciones (`data/tfidf_model.pkl`) es una **fotografía estática regenerada manualmente**, sin ningún job programado ni disparador de CI/CD. Esta sesión encontró que un producto mal etiquetado, corregido manualmente en Shopify hace semanas, seguía apareciendo mal categorizado en producción — no por un bug de código, sino porque nadie había vuelto a ejecutar el script de regeneración (que además tenía su propio bug, no relacionado, que lo hacía fallar en el primer intento). Este es el tipo de deuda técnica que no genera errores audibles: simplemente degrada la calidad de forma silenciosa e indefinida.

La decisión de **no construir la plataforma multi-tenant ahora** (Fase 1b, 23/07) fue y sigue siendo correcta — la evidencia de esta sesión la refuerza: si consolidar la taxonomía de un solo tenant en una única fuente de verdad ha tomado varios meses y sigue incompleto, generalizar esa misma lógica a N tenants ahora habría sido sobre-ingeniería con altísimo riesgo de over-fitting a supuestos equivocados.

No se detectaron regresiones funcionales activas al cierre de esta sesión. Los riesgos identificados son de naturaleza arquitectónica y operacional, no de correctitud puntual del código ya desplegado.

---

## 2. Contexto reconstruido

### 2.1 — Motivación original (documentada, no inferida)

El problema de origen (documento Notion del 03/07/2026, "Gap C") fue observado directamente en producción: una consulta de similitud sobre un producto de la categoría AROS devolvió 8 vestidos y cero aros. La causa raíz de fondo — nunca completamente resuelta y reconocida explícitamente como tal en el propio Plan de Implementación del 09/07 — es fotográfica, no algorítmica: para varias categorías de accesorios (CARTERAS, parte de BRAZALETES), **la galería completa del producto está organizada visualmente alrededor de un vestido/outfit**, confirmado por los propios nombres de archivo de las fotos (`VESTIDOVALENTINAVERDE3.jpg` como imagen principal de un bolso). No existe ninguna foto "correcta" esperando ser indexada — el embedding visual puro de estos productos está genuinamente sesgado hacia la prenda, no hacia el accesorio.

### 2.2 — La respuesta arquitectónica: Composite Embedding

En vez de perseguir una mejor foto (plan explícitamente pausado tras refutarse la hipótesis con evidencia real), la solución adoptada combina el vector de imagen existente con un vector de texto ancla ("earrings aros pendientes...") en una proporción `alpha`, técnica ya validada en producción para otro caso de uso (`search_outfit_by_image`). Esta decisión es sólida: no depende de mejorar el catálogo fotográfico (fuera del control del equipo de ingeniería) y reutiliza un mecanismo ya probado.

### 2.3 — El giro estratégico de Fase 1b (23/07/2026)

Al cerrar la implementación de Composite Embedding para F-08/F-08C, se identificó que el mismo patrón haría falta para F-08B (completar outfit). Antes de implementarlo tácticamente, se pidió explícitamente una revisión arquitectónica considerando una futura evolución multi-tenant. La conclusión de esa revisión — documentada y todavía vigente — es la tesis central que ha gobernado el trabajo desde entonces:

> "El algoritmo... es sólido y se mantiene. El problema real no es el algoritmo — es que el conocimiento de taxonomía... vive hardcodeado como código Python específico de esta tienda, repartido en 3 archivos distintos."

Se decidió explícitamente **no** construir la plataforma multi-tenant completa, y sí dejar una "costura" (seam) correcta: consolidar la taxonomía dispersa en `product_taxonomy.py` como fuente única, migrar los call sites existentes sin cambiar comportamiento, y diferir explícitamente (documentado, no olvidado): config por base de datos, derivación automática de anclas semánticas por centroide, clasificación asistida por LLM, aislamiento de índice FAISS por tenant.

### 2.4 — Lo que ha ocurrido desde entonces (síntesis; detalle en sección 3)

Seis semanas de trabajo iterativo: consolidación parcial de taxonomía, corrección de gaps de cobertura descubiertos reactivamente (NOVIAS CORTOS/MIDIS, NOVIAS CONJUNTOS FALDAS/PANTALONES), una calibración empírica de `alpha` con evidencia real (dirección corregida a mitad de camino tras una autocorrección importante), diagnóstico y corrección de un segundo caso del patrón "bloque gemelo sin fix" (F-08B vs. F-08B.2), dos incidentes de infraestructura no relacionados con el código de recomendación (Supabase pausado, Redis eliminado por inactividad; una dependencia de Python sin techo de versión que rompió el motor de personalización en cada request), y el hallazgo — mediante rastreo de código, no suposición — de que el catálogo interno de recomendaciones es una instantánea estática sin mecanismo de refresco automatizado.

---

## 3. Línea temporal del trabajo realizado

| Fecha | Hito | Estado |
|---|---|---|
| 03/07/2026 | Gap C identificado (F-08 Fase A sin fix vs. F-08C con fix); refutada hipótesis de "mejor foto" | Diagnosticado |
| 03-11/07/2026 | Fix F-08 Fase A (expansión a hermanas + relleno restringido); corrección BRALETTES→top vía estándar de industria (Google Shopping); keep-alive GPT-4o-mini (mismo patrón de gap que LFM) | ✅ Validado |
| 18-23/07/2026 | Composite Embedding Fase 0→3b: POC, implementación, **incidente de integración cross-servicio** (función en un lado, sin endpoint HTTP ni cliente en el otro — 3 días inalcanzable), fix, validación con logs reales | ✅ Cerrado |
| 23-24/07/2026 | Revisión arquitectónica Fase 1b: decisión de consolidar taxonomía sin construir multi-tenant; `product_taxonomy.py` creado; F-08B integrado con boost batcheado | ✅ Cerrado |
| 24-26/07/2026 | Gap NOVIAS LARGOS/ENTERITOS; Caso 1 (mistagging de dato, no de código); Caso 2 (regex de intent "este"); Caso 3 diagnosticado (category_exhausted_info) | ✅ Corregidos |
| 26-27/07/2026 | Calibración de alpha con evidencia real (POC extendido con medición de similitud visual pura y afinidad conceptual); **autocorrección de dirección** (evidencia apuntaba a bajar alpha, no subirlo); alpha_reinforce 0.5→0.3 para COLLARES/BRAZALETES/BRAZALETE | ✅ Aplicado y validado |
| 27-28/07/2026 | Fix de Caso 3 aplicado; observabilidad F-08 Fase A; limpieza de código muerto (`*_category_boost`); auditoría de cobertura vía Shopify (NOVIAS CORTOS/MIDIS agregados) | ✅ Validado |
| 28/07/2026 | **F-08B vs. F-08B.2**: segundo caso documentado del mismo patrón arquitectónico — categoría detectada correctamente, descartada por un mapa hardcodeado más antiguo que nunca contempló accesorio→prenda | ✅ Corregido |
| 30/08-04/09/2026 | Brecha de ~1 mes de inactividad expone: Supabase pausado (tier gratuito), base de datos Redis **eliminada** por inactividad; recreada | ✅ Resuelto (ver riesgo residual, sección 8) |
| 04/09/2026 | `anthropic>=0.25.0` sin techo → rebuild trajo SDK 1.x incompatible → **motor de personalización caía en cada request** | ✅ Corregido y fijado a versión exacta |
| 14-15/09/2026 | "Dress leak": puntuación de especificidad calculada y descartada; producto mal categorizado internamente reaparece pese a estar bien corregido en Shopify — **causa raíz: catálogo interno sin refresco automatizado** | ✅ Corregido (script + regeneración) |
| 15/09/2026 | Gaps de vocabulario: "joyas" nunca fue keyword; patrón relacional no cubría "combina **mejor** este X" | ✅ Corregidos |
| 16/09/2026 | Validación integral: 4 fixes recientes confirmados funcionando juntos, cero regresiones | ✅ Cerrado |

---

## 4. Arquitectura actual

```
                    ┌─────────────────────────┐
   Usuario ──────►  │   Monolito (Cloud Run)   │
                    │  retail-recommender      │
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌──────────────────┐    ┌──────────────────┐
│ TF-IDF +       │     │ mcp_conversation  │    │ LLM (Claude via  │
│ hybrid_        │◄────┤ _handler.py       ├───►│ Anthropic SDK,   │
│ recommender    │     │ (F-08/F-08B/F-08C │    │ fallback GPT-4o- │
│ (data/tfidf_   │     │  + F-08B.2 legacy) │    │ mini, LFM)       │
│  model.pkl,    │     └─────────┬─────────┘    └──────────────────┘
│  ESTÁTICO)     │               │
└───────────────┘               │ HTTP
        ▲                        ▼
        │              ┌──────────────────┐
        │              │ embedding-service │
        │              │ (Cloud Run separado)│
        │              │ FashionSigLIP+FAISS│
        │              └──────────────────┘
        │
        │ (manual, sin automatizar)
┌───────┴────────┐
│ regenerate_    │
│ tfidf_model.py │◄── Shopify Admin API (única conexión en vivo)
└────────────────┘

Estado compartido: Redis Cloud (sesión/turnos) + Supabase/Postgres (KB de paginas)
Fuentes de taxonomía (deberían ser 1, son ≥3):
  product_taxonomy.py (fuente "oficial" desde Fase 1b)
  _B08_SHOPIFY_TO_OUTFIT_CAT (mcp_conversation_handler.py, aún vivo)
  CATEGORY_KEYWORDS / get_parent_categories() (improved_fallback_exclude_seen.py)
  _OUTFIT_COMPLEMENT_MAP (F-08B.2, hardcodeado, aún vivo)
```

**Puntos de diseño que funcionan bien:**
- Separación monolito / embedding-service vía HTTP: límite de servicio limpio, permite escalar/desplegar el modelo visual independientemente.
- `product_taxonomy.py` como estructura declarativa (tipo → outfit_slot, steering_text, alphas) es un buen patrón — el problema no es su diseño, es su adopción incompleta.
- Degradación con gracia ante fallos de Redis/LLM (el sistema sigue respondiendo, con pérdida de continuidad de sesión, no con caída total).

**Puntos de diseño que generan fricción recurrente:**
- Múltiples "bloques gemelos" (Fase A/C, F-08B/B.2) con lógica paralela en vez de compartida.
- Múltiples fuentes de taxonomía activas simultáneamente.
- El catálogo de recomendación (TF-IDF) vive desacoplado de la fuente de verdad real (Shopify) sin mecanismo de sincronización automática.

---

## 5. Estado de cada objetivo

| Objetivo (origen) | Estado | Evidencia |
|---|---|---|
| Corregir dominancia de categoría ajena en similitud (F-08/F-08C) | ✅ Cumplido | Validado con logs reales, múltiples anclas, alpha calibrado empíricamente |
| Extender la técnica a completar-outfit (F-08B) | ✅ Cumplido | Boost batcheado integrado y validado (Fase 1b Paso 4-5) |
| Consolidar taxonomía en una única fuente de verdad | 🟡 Parcial | `product_taxonomy.py` existe y es usado por F-08/F-08C/F-08B boost — pero 3 fuentes paralelas siguen activas y se siguen descubriendo desincronizadas (sección 7) |
| Priorizar la intención explícita del usuario sobre inferencias del ancla | 🟡 Parcial | Corregido en 2 mecanismos distintos (F-08B directo, F-08B.2) en 2 sesiones separadas — cada corrección fue puntual, no una política unificada |
| No construir multi-tenant prematuramente | ✅ Cumplido (decisión vigente) | Explícitamente diferido y documentado; nada de esta sesión lo contradice |
| Sistema con calidad de recomendación auditable/medible | 🟡 Parcial | Existen métricas ad-hoc (% mismo tipo por consulta) pero no un harness de evaluación repetible; cada calibración de alpha requiere una sesión manual nueva |
| Catálogo de recomendación reflejando el estado real de Shopify | 🔴 No cumplido de forma sostenible | Mecanismo existe pero es 100% manual, sin monitoreo de "última sincronización", sin alertas de desfase |

---

## 6. Problemas resueltos

1. **Dominancia visual de prenda sobre accesorio** (F-08/F-08C) — Composite Embedding con alpha calibrado por tipo.
2. **F-08 Fase A sin el mismo fix que F-08C** (Turn 1 vs. Turn 2+) — expansión a hermanas + relleno restringido portado.
3. **F-08B ignoraba la categoría explícita del usuario** (dos veces, dos mecanismos distintos: el camino directo y F-08B.2) — ambos corregidos con evidencia de producción.
4. **Gap de cobertura de taxonomía** (NOVIAS LARGOS/CORTOS/MIDIS/ENTERITOS, NOVIAS CONJUNTOS FALDAS/PANTALONES) — descubiertos reactivamente, corregidos.
5. **Intent detection no reconocía "este" en ciertos patrones** — regex corregido.
6. **Categorías penalizadas por ser contextuales ("con este vestido") se trataban igual que intención real** — puntuación de especificidad, antes descartada, ahora se usa para filtrar.
7. **Vocabulario incompleto** ("joyas" sin mapear, "combina mejor este X" sin patrón) — corregidos con evidencia de producción real.
8. **Incidente de integración cross-servicio** (función sin endpoint ni cliente) — corregido, y capitalizado como aprendizaje de proceso documentado.
9. **Gap de keep-alive** (GPT-4o-mini sin mantenimiento de conexión, mismo patrón que LFM) — corregido.
10. **Infraestructura caída tras inactividad** (Supabase, Redis) — diagnosticada y restaurada.
11. **Dependencia sin techo de versión rompiendo producción** (`anthropic`) — corregida y fijada a versión exacta, verificada contra el paquete real instalado.
12. **Catálogo interno desincronizado del catálogo real** (Lea Calipso) — causa raíz identificada (script de regeneración roto + sin ejecutar), corregido.

---

## 7. Problemas pendientes

1. **Taxonomía sigue repartida en ≥3 fuentes activas.** `_B08_SHOPIFY_TO_OUTFIT_CAT` y `CATEGORY_KEYWORDS`/`get_parent_categories()` no se migraron a `product_taxonomy.py` — cada uno se ha vuelto a desincronizar del resto de forma independiente al menos 2 veces esta sesión (NOVIAS CONJUNTOS ya estaba en `CATEGORY_KEYWORDS` antes de estar en `product_taxonomy.py`; `_OUTFIT_COMPLEMENT_MAP` sigue sin `ZAPATOS` como opción en ninguna entrada).
2. **Sin mecanismo automatizado de sincronización del catálogo TF-IDF.** Depende de que alguien recuerde ejecutar un script manual y redesplegar. No hay alerta de "cuánto tiempo lleva desactualizado".
3. **Fix 2 (prioridad de F-08B.2) sin validación end-to-end confirmada**, pese a múltiples sesiones dedicadas a intentar forzar el escenario exacto. Validado por simulación funcional directa contra el módulo real, no por observación de producción en el camino de código que lo activa.
4. **Inventario cero / productos archivados recomendados activamente** — confirmado repetidamente (4+ veces con evidencia directa), explícitamente diferido por decisión de Yasmani.
5. **T7 — desambiguación de objeto dentro de una misma foto** (el usuario se refiere a un artículo visible en la imagen que no es el producto ancla real) — diagnosticado como una limitación de capacidad, no un bug; sesión dedicada pendiente.
6. **Sin tests automatizados para F-08/F-08B/F-08C**, el área con más cambios y más bugs de todo el sistema en el periodo reconstruido.
7. **Sin harness de calibración repetible para `alpha`** — cada ajuste (COLLARES/BRAZALETES, TOCADOS, CINTURONES) fue una sesión manual con 2-6 anclas.

---

## 8. Deuda técnica y riesgos

### Deuda técnica

| Ítem | Tipo | Ubicación |
|---|---|---|
| 3+ fuentes de taxonomía paralelas | Duplicación | `product_taxonomy.py`, `mcp_conversation_handler.py`, `improved_fallback_exclude_seen.py` |
| `_OUTFIT_COMPLEMENT_MAP` hardcodeado, incompleto en su propia dirección | Workaround específico de tienda | F-08B.2 |
| Regeneración del catálogo TF-IDF vía script manual sin orquestación | Solución específica del entorno actual | `regenerate_tfidf_model.py` |
| Bloques "gemelos" con lógica duplicada (Fase A/C; F-08B/B.2) | Acoplamiento incorrecto / responsabilidad distribuida | `mcp_conversation_handler.py` |
| `except Exception` amplios que enmascaran errores de integración sin generar `ERROR` visible | Código temporal con costo de observabilidad | Confirmado como causa de un incidente de 3 días (Fase 3) |
| Dependencias con piso de versión abierto (`anthropic>=`, antes también `httpx>=`) sin auditoría del resto del `requirements.txt` | Riesgo de reproducibilidad de build | `requirements.txt` |

### Riesgos activos

- **Redis Cloud y Supabase siguen en tier gratuito.** El problema de fondo (auto-pausa/auto-eliminación por inactividad) no se resolvió, solo se recreó el síntoma. Volverá a ocurrir tras el próximo periodo de inactividad prolongada, salvo cambio de plan o mecanismo de "keep-alive" de infraestructura.
- **El patrón "bloque gemelo sin el mismo fix" es estructural, no accidental.** Con 2 ocurrencias documentadas en 2 meses, es razonable esperar una tercera si se sigue extendiendo funcionalidad sin unificar la lógica de decisión de categoría en un solo lugar.
- **Ningún otro paquete de `requirements.txt` fue auditado** tras el incidente de `anthropic` — el mismo patrón (piso abierto + rebuild tras inactividad) podría repetirse con cualquier otra dependencia.
- **La calidad medida (% mismo tipo) puede estar sistemáticamente inflada o distorsionada** por la mezcla de productos archivados/sin stock en el índice — no sabemos, sin resolver el ítem pendiente #4, cuánto de la "escasez" observada en categorías como ZAPATOS es escasez real de catálogo vendible o ruido de productos no comprables.

---

## 9. Evaluación de Visual Search / Composite Embedding Granular

**Qué problema pretende resolver:** dominancia de categorías visualmente vecinas (típicamente por sesgo fotográfico) sobre el tipo real del producto ancla, en tres rutas de búsqueda (similitud Turn 1, similitud Turn 2+, completar-outfit).

**Arquitectura propuesta (documentada, 09/07):** combinar vector de imagen + vector de texto ancla por tipo Shopify específico, con `alpha` como parámetro explícito y distinto según el uso (reforzar tipo propio vs. pedir tipo distinto).

**Estado actual — diferenciando diseño, implementación y comportamiento validado:**

| Capa | Estado |
|---|---|
| Diseño documentado (09/07) | Completo, dos piezas (prompts por tipo + función de boost), interfaz `alpha` parametrizada desde el inicio |
| Implementación real | Evolucionó más allá del diseño original: migró de `SHOPIFY_TYPE_TEXT_PROMPTS` (embedding-service) a resolución de texto en el monolito vía `product_taxonomy.py` (Fase 1b, "Opción B") — **el diseño documentado en el Plan de 09/07 ya no describe fielmente el código actual**, aunque el DCT de Fase 1b sí lo hace |
| Comportamiento validado | Confirmado con logs reales para AROS (92-100%), CARTERAS (92%), COLLARES/BRAZALETES post-calibración (61-83%), TOCADOS (mejorado tras calibración de Yasmani) |

**Coherencia diseño↔implementación:** alta para la Fase 1-3b (documentada fielmente en su propio DCT de cierre). Baja si se compara contra el documento *original* de 09/07, que describe una arquitectura (prompts en el embedding-service) que fue deliberadamente reemplazada — el propio Plan de Fase 1b lo señala explícitamente como decisión consciente ("Opción B"), no es un descuido, pero significa que el Plan de 09/07 debe leerse como *contexto histórico*, no como especificación vigente.

**Dependencias que introduce:** acopla la calidad de recomendación de accesorios a prompts de texto escritos a mano en español/inglés por tipo — si se cambiara el modelo de embeddings (FashionSigLIP → otro), estos prompts y sus alphas asociados tendrían que recalibrarse desde cero, sin ninguna capa de abstracción que amortigüe el cambio.

**Encaje con el resto del sistema:** bueno a nivel de integración (aditivo, sin romper caminos existentes); débil a nivel de gobernanza de datos (steering_text y alpha viven en `product_taxonomy.py`, pero la *detección* de qué categoría pedir sigue dependiendo de `CATEGORY_KEYWORDS`, una fuente distinta).

---

## 10. Gap Analysis

```
VISIÓN OBJETIVO (Plan 09/07 + revisión Fase 1b 23/07)
   "Consultas de accesorios deben respetar el tipo real del producto,
    con una única fuente de verdad de taxonomía, sin construir
    multi-tenant prematuramente"
       ↓
ARQUITECTURA DISEÑADA (Fase 1b, Pasos 1-6)
   product_taxonomy.py como fuente única; migración de los 3 call
   sites existentes; batching FAISS; integración F-08B aditiva
       ↓
IMPLEMENTACIÓN ACTUAL
   product_taxonomy.py existe y gobierna alpha/steering_text para
   F-08/F-08C/F-08B-boost — PERO _B08_SHOPIFY_TO_OUTFIT_CAT,
   CATEGORY_KEYWORDS y _OUTFIT_COMPLEMENT_MAP NO fueron migrados;
   siguen siendo fuentes activas e independientes
       ↓
COMPORTAMIENTO VALIDADO
   Funciona correctamente en todos los casos probados HOY — pero
   cada gap nuevo descubierto esta sesión (NOVIAS CONJUNTOS, "joyas",
   "combina mejor") confirma que las fuentes siguen desincronizándose
```

| # | Gap | Capa donde diverge | Severidad |
|---|---|---|---|
| 1 | Taxonomía en 3+ fuentes en vez de 1 (objetivo explícito de Fase 1b, incumplido) | Diseñada → Implementada | 🟠 Alto |
| 2 | Catálogo de recomendación (TF-IDF) sin sincronización automatizada con Shopify | Ningún plan lo contempló explícitamente — gap de visión, no solo de implementación | 🔴 Crítico |
| 3 | Patrón "bloque gemelo" repetido sin resolver la causa de fondo | Diseñada → Implementada | 🟠 Alto |
| 4 | Plan original de 09/07 ya no describe la arquitectura real (superado por "Opción B" de Fase 1b) | Documentación desactualizada | 🟡 Medio |
| 5 | Sin tests automatizados en el área de mayor cambio | Implementada → Validada (validación es 100% manual, no repetible) | 🟠 Alto |
| 6 | Productos sin stock/archivados en el índice de recomendación | Ningún plan lo contempló — gap de visión | 🟡 Medio (🟠 si se confirma que distorsiona las métricas de calidad ya medidas) |
| 7 | T7 (desambiguación multi-objeto en una foto) — capacidad nunca estuvo en el alcance de ningún plan | Visión objetivo nunca lo incluyó | 🟢 Bajo (no es una regresión, es un límite conocido de alcance) |
| 8 | Infraestructura (Redis/Supabase) en tier gratuito, susceptible a repetir el incidente de inactividad | Operacional, fuera del código | 🟡 Medio |

---

## 11. Evaluación de escalabilidad y multi-tenant

La decisión de Fase 1b de **no** construir la plataforma multi-tenant ahora sigue siendo, con la evidencia de esta sesión, la decisión correcta — y hay un argumento más fuerte para sostenerla del que había en julio: **si consolidar la taxonomía de un solo tenant ha tomado dos meses y sigue incompleta**, la generalización a N tenants habría heredado exactamente los mismos problemas (fuentes múltiples, bloques gemelos) multiplicados por tenant, con el agravante de que cada nuevo gap de cobertura (como los encontrados esta sesión) tendría que resolverse N veces en vez de una.

Dicho esto, hay una tensión real que vale la pena nombrar explícitamente: **el trabajo de esta sesión ha sido, en su mayoría, hardening reactivo de un solo tenant** (encontrar y corregir gaps de cobertura, vocabulario, y sincronización uno por uno, según se descubren en producción). Ninguno de los 4 puntos explícitamente diferidos en Fase 1b (config por DB, centroides automáticos, clasificación por LLM, FAISS por tenant) ha avanzado. Esto no es necesariamente un problema — pero significa que la "costura" que se prometió dejar lista para el tenant #2 sigue siendo, en la práctica, tan específica de esta tienda como antes de la revisión arquitectónica, solo que ahora vive en un archivo en vez de tres cuartos.

**Sobre IA / evolución de modelos:** la arquitectura separa razonablemente el LLM conversacional (con fallback entre proveedores ya construido) del modelo de embeddings visuales (FashionSigLIP, aislado en su propio servicio). Sin embargo, la lógica de *negocio* de recomendación (qué texto usar para "anclar" cada tipo, qué alpha usar) está tan íntimamente ligada al modelo de embeddings actual que un cambio de modelo requeriría, en la práctica, repetir el trabajo de calibración de alpha completo — no hay una capa de abstracción entre "estrategia de recomendación" y "modelo de embeddings específico" que amortigüe ese cambio.

---

## 12. Fortalezas actuales

- **Disciplina de diagnóstico con evidencia real** — cada fix de esta sesión (y del historial revisado) se sustenta en logs de producción reales, no en suposiciones; varias veces el propio proceso corrigió hipótesis iniciales erróneas antes de aplicar un cambio.
- **Cambios aditivos, bajo riesgo de regresión** — el patrón consistente de "nunca tocar la lógica ya validada, solo agregar" ha mantenido el sistema estable pese al volumen de cambios.
- **Separación de servicios limpia** entre el monolito y el embedding-service.
- **Capacidad de autocorrección documentada** — la propia revisión de julio (alpha "más alto" vs. "más bajo") y esta sesión (la hipótesis de "recomendaciones congeladas" descartada con evidencia antes de reportarla como definitiva) muestran un proceso que se corrige a sí mismo en vez de aferrarse a la primera explicación plausible.
- **Decisión arquitectónica de julio sobre multi-tenant** — evaluada hoy con más contexto, se sostiene.

---

## 13. Aspectos que requieren reconsideración

1. **La consolidación de taxonomía debería tratarse como incompleta, no como cerrada.** El backlog ya la prioriza (script de auditoría por centroides), pero vale la pena reconocer explícitamente que el objetivo original de Fase 1b ("una única fuente de verdad") no se ha cumplido, y decidir si vale la pena una sesión dedicada exclusivamente a terminar la migración de los 3 call sites restantes, en vez de seguir parchando cada fuente por separado cuando se descubre un gap.
2. **La regeneración del catálogo TF-IDF necesita dejar de ser un script manual.** Como mínimo, un mecanismo que registre y exponga "cuándo fue la última sincronización exitosa", para que un desfase de semanas sea visible antes de que un usuario lo note.
3. **El patrón de bloques gemelos merece una decisión explícita**, no otro parche puntual la próxima vez que aparezca: ¿vale la pena invertir en unificar F-08/F-08B/F-08C/F-08B.2 detrás de una sola función de "resolución de categoría objetivo", aunque sea con mayor costo de refactor ahora, para dejar de pagar el costo de encontrar la tercera y cuarta ocurrencia del mismo patrón?
4. **Decidir el destino de `_OUTFIT_COMPLEMENT_MAP` y F-08B.2 en general** — es un mecanismo de fallback más antiguo y menos capaz que el camino principal; ahora que el camino principal es más robusto, vale la pena evaluar si F-08B.2 debería reducir su alcance, o si su rol como red de seguridad todavía se justifica.

---

## 14. Prioridades estratégicas

1. **Automatizar (o al menos monitorear) la sincronización del catálogo TF-IDF.** Es el gap con mayor potencial de degradación silenciosa y ya causó un incidente confirmado.
2. **Auditar el resto de `requirements.txt`** contra el mismo patrón que rompió `anthropic` (piso de versión abierto).
3. **Decidir el futuro de la consolidación de taxonomía** — completarla o aceptar formalmente que quedará repartida, pero dejar de tratarla como "casi terminada".
4. **Abordar inventario/archivados** — no solo por calidad de recomendación percibida, sino porque puede estar distorsionando cada métrica de "% mismo tipo" medida hasta ahora.
5. **Sesión dedicada a T7** — es una decisión de alcance de producto (¿vale la pena la inversión en detección de objetos?), no un fix de código.

---

## 15. Roadmap recomendado

**Corto plazo (próximas 1-2 sesiones):**
- Job o alerta de sincronización del catálogo TF-IDF.
- Auditoría rápida de pines de versión en `requirements.txt`.
- Cerrar la validación pendiente de Fix 2 con un enfoque distinto a la repetición (ver sección 7, punto 3).

**Mediano plazo:**
- Diseño de un harness mínimo de calibración de alpha (aunque sea un script reutilizable, no un framework completo) para dejar de repetir el proceso manual cada vez que aparece un tipo nuevo con dominancia visual.
- Decisión explícita sobre unificar la resolución de categoría objetivo entre F-08/F-08B/F-08C/F-08B.2.
- Resolver inventario/productos archivados en el índice.

**Largo plazo (condicionado a que un segundo tenant esté genuinamente cerca):**
- Retomar los 4 puntos diferidos en Fase 1b (config por DB, centroides automáticos, clasificación por LLM, FAISS por tenant) — no antes, dado que la base de un solo tenant sigue consolidándose.

---

## 16. Preguntas abiertas / información faltante

- ¿Existe (fuera de esta documentación local) un registro de qué otros DCTs o decisiones viven solo en Notion y no se han sincronizado a este repositorio? El documento `DCT — Propagación...` es un export de Notion — no está claro si es la versión más actualizada o si Notion tiene contenido posterior no reflejado aquí.
- ¿Cuál es la cadencia real de cambios en el catálogo de Shopify (altas, bajas, recategorizaciones)? Sin ese dato, no es posible dimensionar qué tan urgente es automatizar la sincronización del TF-IDF versus, por ejemplo, un recordatorio semanal manual.
- ¿Hay un plan de negocio o fecha estimada para un segundo tenant? Determina directamente si la sección 15 ("largo plazo") debería moverse a mediano plazo.
- ¿Se ha auditado el resto de `requirements.txt` en algún momento anterior a este incidente? No encontré evidencia de ello en la documentación revisada.
