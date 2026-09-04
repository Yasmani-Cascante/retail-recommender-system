
# BACKLOG — Búsqueda dirigida por atributos (color, y potencialmente otros)


**Fecha:** 24/07/2026
**Estado:** Idea documentada, sin empezar — no confundir con un PLAN activo
**Origen:** Pregunta de Yasmani durante la validación de Fase 1b — "¿el sistema puede responder 'vestidos similares pero de color verde'?"
**Relacionado con:** `PLAN_Fase1b_Revision_Arquitectonica_23072026.md` (mismo directorio) — reutiliza directamente la infraestructura construida ahí.

---

## 1. Respuesta corta a la pregunta original

**Hoy no funciona** — no existe ningún intent, parsing, ni lógica que combine "similar a X" con un atributo como color. **Es técnicamente factible**, y gran parte de la infraestructura necesaria ya existe (construida para Fase 1b sin saber que serviría para esto también) — pero faltan piezas concretas, detalladas abajo. No es "ya casi funciona"; es "la mitad del camino ya está hecho".

---

## 2. Lo que ya existe y es 100% reutilizable

`search_by_product_id_with_text_boost()` (`visual_retriever.py`, embedding-service — Fase 1b Paso 2) no tiene ningún conocimiento de "tipo de producto" a nivel de diseño. Internamente solo hace:

```python
composite = alpha * image_np + (1 - alpha) * text_np
```

`text_np` puede venir de **cualquier texto** — hoy le mandamos "necklace collar cadena..." (tipo), pero mecánicamente podría ser "green vestido verde" (color) sin ningún cambio en `visual_retriever.py`, `main.py`, ni `colbert_client.py`. La función, el endpoint (`/v1/embed/search-by-id-with-text-boost`) y el método cliente ya aceptan texto arbitrario — no hay ninguna validación que lo restrinja a categorías.

Confirmado contra documentación real (HuggingFace / Marqo) en sesión anterior: FashionSigLIP fue entrenado con Generalised Contrastive Learning sobre categorías, estilos, **colores**, materiales y palabras clave — no solo descripciones largas. La capacidad del modelo ya cubre esto; lo que falta es aplicación, no modelo.

---

## 3. Lo que falta (piezas concretas, no un solo bloque)

### 3.1 — Detección de intent
Hoy nada extrae "verde" de una consulta como "vestidos similares pero verdes" y lo separa de la intención de similitud. Necesita su propio paso de extracción (parecido a como ya se extrae tipo/categoría del texto en varios puntos del sistema) — probablemente una lista de colores conocidos (español + variantes) más el patrón "pero de color X" / "pero en X".

### 3.2 — Calibración de alpha propia para color (el paso más importante, no dar por sentado)
`alpha=0.5` (reforzar tipo) y `alpha=0.2` (pedir tipo distinto) salieron de la Fase 0 — un POC con casos reales, no un número teórico. Color es un eje semántico distinto; no hay ninguna evidencia de qué alpha haría que el modelo empuje genuinamente hacia "verde" sin perder la similitud visual con el ancla. **Necesita su propio mini-POC**, misma metodología que Fase 0: puñado de casos reales, probar 2-3 valores de alpha, medir cuántos resultados son genuinamente del color pedido.

### 3.3 — Red de seguridad (validación contra dato real, no solo confiar en el embedding)
El composite embedding es un empujón suave — el modelo "cree" que algo se ve verdoso, no hay garantía. Mismo patrón que `_b08_belongs_to_bucket()` (Fase 1b, fix del 24/07): verificar el resultado contra el dato real del catálogo antes de mostrarlo. Para esto hace falta primero **confirmar cómo está tageado el color real en Shopify** (¿variante de producto, tag, campo custom, ninguno de forma confiable?) — sin eso, no se puede construir la validación dura.

### 3.4 — Combinar 3 señales, no 2
"Vestidos similares **pero** verdes" en realidad pide imagen + tipo + color simultáneamente — ya no es un blend de 2 (lo que existe hoy), potencialmente de 3. No hay evidencia de cómo se comporta esa combinación (¿pesos fijos para los 3? ¿se aplica primero refuerzo de tipo y color como paso separado de re-ranking sobre ese resultado, en vez de un blend único de 3 vectores?). Esto es una decisión de diseño a resolver en el POC, no algo a asumir de antemano.

---

## 4. Por qué esto encaja bien con la visión de plataforma SaaS

A diferencia de `product_type` (vocabulario específico de cada merchant, ya nos costó varios bugs de cobertura — BRALETTES, BRAZALETE, ZAPATOS, NOVIAS...), los colores son un concepto casi universal entre catálogos de moda. Si se calibra bien, esta capacidad sería genuinamente más portable entre tenants que el trabajo de taxonomía que acabamos de hacer — vale la pena tenerlo en mente si esto se prioriza antes que la iniciativa de config por tenant.

---

## 5. Primer paso sugerido cuando se retome (no ahora)

Antes de cualquier código: confirmar en Shopify Admin cómo está representado el color en el catálogo real (igual que se hizo para `CLUTCH` el 24/07 — revisar directamente en vez de asumir). Eso determina si 3.3 (red de seguridad) es viable desde el día uno o si primero hay que mejorar el tageo de color en el catálogo.
