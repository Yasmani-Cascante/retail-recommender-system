# Prompt de continuidad — pegar como primer mensaje en una sesión nueva

Retomamos trabajo en el sistema de recomendaciones de `ai-shoppings.myshopify.com` (proyecto GCP `retail-recommendations-449216`, región `us-central1`). Repo local en `C:\Users\yasma\Desktop\retail-recommender-system`.

## Antes de nada, lee esto para recuperar el contexto completo

1. **`docs\0_plans\Transformers\Visual_search\Composite_Embedding_Granular\Evaluacion_Integral_16092026\DCT_Cierre_Sesion_01102026.md`** — el cierre de la sesión anterior, con un resumen de los cuatro bloques de trabajo recientes y el hallazgo con el que se cerró (ver punto 3 de este prompt).
2. Si necesitas el detalle técnico completo de la unificación de taxonomía o de la herramienta de auditoría de catálogo, esos dos DCTs están en el mismo directorio — el de cierre de sesión te dirá exactamente cuál leer para qué.
3. Memoria de este proyecto: `/projects/1df658d6-d36e-4186-b1f5-64fb3cc5b5c1/learnings.md` ya tiene algunos aprendizajes técnicos duraderos (gotchas de FAISS, IAM de Cloud Run, Shopify API) — revísalo también.

## Cómo trabajamos — por favor, mantén este estilo

- **Evidencia primero, nunca asumas.** Antes de explicar cómo funciona algo o de proponer un fix, lee el código real (no actúes solo por lo que recuerdes de esta conversación). Si hay una duda sobre comportamiento, créalo con un caso sintético antes de tocar el repo real.
- **Dry-run antes de aplicar.** Cuando edites archivos del repo real, usa `dryRun: true` primero en `edit_file`, revisa el diff, y solo entonces aplica de verdad.
- **Validar siempre.** Después de cualquier cambio: `ast.parse` para sintaxis, y si es lógica nueva, un test rápido con datos sintéticos antes de darla por buena.
- **Documentar mientras se trabaja**, no al final — los DCT de esta carpeta son la referencia que se mantiene viva, no un registro histórico que se escribe una sola vez.
- Yasmani es Senior Software Architect & QA Engineer — análisis riguroso y basado en evidencia, no resúmenes superficiales.

## Dónde quedamos — el hilo abierto

La sesión anterior cerró con una pregunta que quedó **respondida pero no resuelta**: ¿está completa la unificación de la lógica de resolución de categoría entre las cuatro rutas del sistema (F-08 Fase A, F-08B, F-08C, F-08B.2)?

**Respuesta confirmada revisando el código real:** no. F-08B (completar outfit, camino principal) y F-08B.2 (respaldo) ya están unificados — ambos usan `product_taxonomy.get_outfit_slot()`, con su lógica extraída a funciones puras y probadas (`f08b_target_categories.py`, `f08b2_category_resolution.py`). **F-08 Fase A y F-08C siguen con su propio mecanismo** (`get_parent_categories()`, expansión a categorías "hermanas"), sin extraer, sin tests — y con una divergencia concreta entre ellos mismos, documentada en el propio código desde julio y nunca resuelta: un fix de F-08C (el "relleno restringido" del 17/06/2026) nunca se portó a F-08 Fase A, con una nota explícita del autor original pidiendo evaluarlo "en una sesión futura".

## Próximo paso acordado

Investigar a fondo el código real de F-08 Fase A y F-08C en `src/api/core/mcp_conversation_handler.py` (buscar los bloques marcados `F-08 Fase A` y `F-08C` en comentarios) — mapear con precisión qué lógica es compartida de hecho y cuál diverge, antes de decidir si conviene extraerla a funciones puras como se hizo con F-08B/F-08B.2, o si el enfoque correcto es distinto, dado que estas dos rutas resuelven un problema diferente (similitud visual con expansión a categorías hermanas, no completar un outfit con conflictos de slot).

No asumas que el patrón de extracción de F-08B/F-08B.2 se traslada igual aquí — confírmalo leyendo el código primero.
