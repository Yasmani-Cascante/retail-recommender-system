# RFC — F-02 Evolución: KB Contextualizer + size_profile para queries de talla — 12 Abr 2026

## Tesis

La clasificación INFORMATIONAL para preguntas de talla es correcta y debe mantenerse. El problema no es el routing, sino que el early return del KB ignora el contexto disponible. La solución es enriquecer la respuesta KB, no cambiar la arquitectura de intent detection.

---

## El gap actual

Cuando un usuario logueado, con historial conocido, en página de producto pregunta "¿qué talla me recomiendas?", el sistema tiene tres piezas de información que el documento genérico ignora:

```
1. size_profile: {ENTERITOS: "S" (100%), VESTIDOS: "S" (66%)}
2. product_context: {type: "ENTERITOS CORTOS", collections: ["Enteritos", "Fiesta"]}
3. market_id: "CL"
```

Devolver el documento de guía de tallas genérico en ese contexto es un **fallo de producto**, no un fallo técnico.

---

## Análisis de casos

### Caso A: ¿Qué tallas tienen? (disponibilidad)

Requiere datos del producto actual, no del historial. Extensión natural de `kb_contextualizer.py` pasando `product_context`.

### Caso B: ¿Qué talla me recomiendas? (recomendación personal)

El caso de mayor valor. Tres opciones evaluadas:

| Opción | Enfoque | Riesgo | Recomendación |
| --- | --- | --- | --- |
| 1 | Contextualizar KB con size_profile via Haiku | Bajo | ✅ Implementar |
| 2 | Nuevo path híbrido bypassing KB | Medio | ⚠️ Futuro |
| 3 | Cambiar clasificación del intent detector | Alto | ❌ No recomendado |

### Caso C: Feedback de otros clientes

Requiere datos de reviews/devoluciones. No disponible actualmente. Roadmap largo plazo.

---

## Evolución recomendada

### Paso 1 — Enriquecer kb_contextualizer con size_profile + product_context

**Complejidad: Baja. Tiempo estimado: 1–2 días.**

Extender `generate_contextual_answer()` en `kb_contextualizer.py` para aceptar y usar `size_profile` y `product_context` cuando el sub_intent es `product_sizing`.

```python
# En el handler, cuando sub_intent == product_sizing:
contextual_answer = await generate_contextual_answer(
    query=conversation_query,
    kb_document=kb_answer.answer,
    sub_intent=intent_result.sub_intent,
    language=language,
    anthropic_client=anthropic_client_for_kb,
    # NUEVO:
    size_profile=getattr(mcp_context, "size_profile", None),
    product_context=getattr(mcp_context, "current_product_context", None),
)
```

Prompt para Haiku cuando hay datos de usuario:

```
Documento de política de tallas: {kb_document}
Producto actual: {product_type} — {title}
Historial del cliente: talla habitual en {category} = {size} ({confidence}% confianza)

Responde la pregunta del usuario usando PRIMERO el historial si es relevante,
luego el documento. Si no hay historial, usa solo el documento.
```

Resultado esperado: "Según tus compras anteriores, en enteritos sueles pedir talla S — y este modelo está disponible en tu talla."

### Paso 2 — Variantes del producto en product_context (implementación futura)

Hoy `product_context` incluye `variants_count` pero no la lista de variantes disponibles. Cuando se implemente ese enriquecimiento (via Shopify GraphQL), las queries de disponibilidad ("¿qué tallas tienen?") podrán responder específicamente sin cambiar el intent path.

---

## Lo que NO se debe cambiar

La clasificación INFORMATIONAL para preguntas de talla **es correcta**. Cambiar la clasificación (Opción 3) crearía acoplamiento entre el detector de intents y el estado conversacional, rompiendo la separación de responsabilidades y haciendo el detector mucho más difícil de testear.

---

## Tabla resumen de madurez

| Situación | Actual | Correcto | Complejidad |
| --- | --- | --- | --- |
| Sin historial, pregunta genérica de tallas | KB genérico ✅ | KB genérico | 0 |
| Con historial, pregunta de talla personal | KB genérico ❌ | KB + size_profile via Haiku | Baja |
| Sin historial, consulta disponibilidad | KB genérico ❌ | KB + variantes del producto | Media |
| Con historial, consulta disponibilidad | KB genérico ❌ | KB + variantes + size_profile | Media |
| Feedback de otros clientes | No aplica | Requiere datos de reviews | Alta |