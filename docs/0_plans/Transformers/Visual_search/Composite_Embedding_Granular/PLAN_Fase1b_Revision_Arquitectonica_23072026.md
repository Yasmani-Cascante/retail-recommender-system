
# PLAN — Fase 1b: Diseño Revisado (post revisión arquitectónica)

**Fecha de apertura:** 23/07/2026
**Estado:** CERRADO (24/07/2026) — ver DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md (raíz del repo) para el resumen final
**Precede a:** DCT de cierre de Fase 1b (aún no existe)
**Documentos relacionados:**
- `Plan_de_Implementacion_09072026.md` (mismo directorio) — plan original de Composite Embedding Granular, Fase 0
- `DCT_Composite_Embedding_Fase1_a_3b_Cierre_23072026.md` (raíz del repo) — cierre de Fase 1→3b (F-08/F-08C), que identificó el gap que esta fase ataca
- Notion: sección "Sesión de cierre — Composite Embedding Granular, Fase 1 a Fase 3b" en la página "DCT — Propagación Fix F-08C → F-08 Fase A"

---

## 1. Por qué existe este documento

Al cerrar Fase 1→3b, propuse un primer diseño táctico de Fase 1b (llamadas paralelas por tipo, α=0.2, hardcodeando un cuarto diccionario de taxonomía). Antes de implementarlo, Yasmani pidió una revisión estratégica completa (rol Staff/Principal Architect + CTO) considerando la evolución hacia una plataforma SaaS multi-tenant para múltiples tiendas Shopify de moda, cada una con catálogo, taxonomía, idioma y tamaño propios.

**Conclusión de la revisión**: el algoritmo (composite embedding dirigido por tipo, vía llamadas paralelas) es sólido y se mantiene. El problema real no es el algoritmo — es que el *conocimiento de taxonomía* (qué tipos existen, cómo se llaman, a qué slot de outfit pertenecen, qué texto los describe) vive hardcodeado como código Python específico de esta tienda, repartido en 3 archivos distintos. Ese acoplamiento ya generó bugs reales con un solo tenant (BRALETTES mal clasificado, BRAZALETE singular ausente, ZAPATOS sin mapeo) — con más tenants, ese patrón de fallo se multiplica.

**Decisión**: no construir la plataforma multi-tenant completa ahora (sería sobre-ingeniería prematura con un solo cliente hoy). Sí dejar la "costura" (seam) correcta para no pagar el costo completo de retrofit cuando llegue el tenant #2.

---

## 2. Alcance de esta fase (lo que SÍ se hace ahora)

1. **Consolidar la taxonomía dispersa** en un único módulo/estructura con un esquema explícito (tipo → slot de outfit, prompt de texto, α sugerido) — reemplaza `SHOPIFY_TYPE_TEXT_PROMPTS` (visual_retriever.py), `_B08_SHOPIFY_TO_OUTFIT_CAT` (mcp_conversation_handler.py) y el uso relevante de `CATEGORY_KEYWORDS["ACCESSORIES"]` (improved_fallback_exclude_seen.py) por una sola fuente de verdad. Sigue siendo un dict/JSON por ahora (un solo tenant) — el punto es la interfaz única, no la tecnología de almacenamiento.
2. **Migrar los call sites existentes** (Fase 1/3b ya desplegados) a leer de esta config consolidada, sin cambiar comportamiento — refactor puro, validar que nada se rompe antes de construir nada nuevo encima.
3. **Batchear las llamadas de boost por tipo** en una sola búsqueda FAISS con múltiples vectores compuestos, en vez de N round-trips HTTP paralelos — mejora latencia y la historia de escalabilidad a catálogos con más tipos.
4. **Implementar la integración real en F-08B** (el diseño aditivo ya esbozado: agregar candidatos a `_b08_outfit_cats` por tipo, sin tocar la lógica downstream ya validada — mismo-tipo, interleaving por subtipo, pools fresh/full).
5. Desplegar y validar con logs reales, mismo rigor que Fase 1→3b.

## 3. Explícitamente diferido (no ahora, documentado para no perderlo)

- Config de taxonomía respaldada por base de datos (Supabase), editable por tenant sin redeploy.
- Derivación automática del "ancla semántica" por tipo desde centroides del propio catálogo (en vez de prompts de texto escritos a mano) — alternativa que la vuelve independiente de idioma/vocabulario del merchant.
- Clasificación asistida por LLM (Claude) de `product_type` → slot de outfit al onboardear un tenant nuevo.
- Aislamiento de índice FAISS por tenant (hoy es un índice compartido para una tienda).

Estos quedan como iniciativa arquitectónica separada, a retomar cuando un segundo tenant esté cerca del horizonte.

---

## 4. Plan paso a paso

- [x] **Paso 1** — Disenado y creado `src/recommenders/product_taxonomy.py` (unica fuente de verdad: 24 tipos, outfit_slot + steering_text opcional + alpha_reinforce/alpha_complement por tipo). Validado con py_compile + smoke test de las funciones de lookup.
- [x] **Paso 2** — Migrados los call sites ya desplegados. Se opto por **Opcion B** (texto resuelto en el monolito, embedding-service generico) en vez de duplicar taxonomia -- cambia el contrato de Fase 3b, pero de forma aditiva (endpoint/metodo/funcion nuevos en paralelo a los viejos, sin ventana de deploy rota). Tocados: visual_retriever.py (+search_by_product_id_with_text_boost, +_text_boost_cache lazy), main.py (+endpoint /v1/embed/search-by-id-with-text-boost), colbert_client.py (+metodo cliente), mcp_conversation_handler.py (F-08 Fase A + F-08C migrados a product_taxonomy.get_steering_text()/get_alpha()). Validado: sintaxis OK en los 4, contrato cruzado endpoint<->cliente OK, logica T8/hermanas intacta. Comportamiento identico (alpha=0.5 para los 9 tipos, mismo texto). Pendiente: deploy + validacion con logs reales.
- [x] **Paso 3** — Busqueda FAISS batcheada implementada. `visual_retriever.py`: nuevo metodo `search_by_product_id_with_multi_text_boost()` -- resuelve N textos (cache hits directos, misses en un solo batch encode), arma una matriz (N, embed_dim) de vectores compuestos, y hace **una sola** llamada a `faiss_index.search()` para las N consultas (en vez de N llamadas HTTP + N busquedas FAISS separadas). `main.py`: nuevo endpoint POST `/v1/embed/search-by-id-with-multi-text-boost` (POST en vez de GET -- una lista de N textos no calza bien en query params). `colbert_client.py`: metodo cliente correspondiente. Cache de texto compartido con el metodo singular de Paso 2 (mismo formato). Validado: sintaxis OK en los 3, contrato POST cruzado OK. Pendiente de usar (Paso 4).
- [x] **Paso 4** — Integrado en F-08B. Justo despues de construir `_b08_outfit_cats`, se agrupan los tipos hermanos por `alpha_complement` (hoy: un solo grupo, 0.2 para los 9 tipos de ACCESSORIES), se pide UNA llamada batcheada por grupo via `search_by_product_id_with_multi_text_boost()`, y los resultados se agregan (no reemplazan) a `_b08_outfit_cats[bucket]`. Toda la logica downstream (mismo-tipo, interleave por subtipo, pools fresh/full, fix de loop infinito) opera sin cambios sobre la lista combinada -- verificado que sigue presente. Validado: sintaxis OK, diff 100% aditivo (cero lineas removidas). Pendiente de desplegar y confirmar con logs reales que T3 (antes: 1 producto) ahora trae variedad real.
- [x] **Paso 5** — Desplegado ambos servicios, validado con 6 consultas de prueba (23/07/2026 revision `retail-recommender-00269-szm`). Confirmado: F-08/F-08C sin regresion (alpha=0.5 identico, opt-in correcto -- no activa para VESTIDOS LARGOS, tipo sin steering_text). F-08B Fase 1b activo en las 3 consultas de "combinar": `F-08B Fase 1b: 8-9 tipos con boost dirigido` en cada una, llamadas batcheadas exitosas (9/9, 8/8, 8/8 textos con resultados). Pool crudo pre-filtro con variedad genuina confirmada. Generaliza bien incluso para anclas fuera de la familia ACCESSORIES (ancla VESTIDO pidiendo accesorios). Cero errores, cero AttributeError. Hallazgo abierto: bucket "bag" siempre 100% CARTERAS en las 3 pruebas, nunca CLUTCH -- llamada exitosa pero sin resultados CLUTCH-tipados; posible catalogo con poco/nulo inventario CLUTCH real, a confirmar con Yasmani. Pendiente: confirmar composicion de tipos de los productos FINALES (post-filtro) contra observacion directa del widget -- los logs solo muestran IDs en ese punto. **CONFIRMADO por Yasmani (24/07/2026): buena variedad real de tipos en el widget para T3/T5/T6.** No se considero necesaria una prueba adicional puntual (ancla AROS + combinar) -- la evidencia actual (3 anclas distintas: VESTIDO, COLLARES, CARTERAS) se considera suficiente.
- [x] **Paso 6** — DCT de cierre de Fase 1b creado: `DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md`. Este documento (PLAN) queda como referencia historica del diseno.

---

## 5. Bitácora

**23/07/2026** — Documento creado. Revisión arquitectónica completa (ver sección 1). Listo para comenzar Paso 1.
