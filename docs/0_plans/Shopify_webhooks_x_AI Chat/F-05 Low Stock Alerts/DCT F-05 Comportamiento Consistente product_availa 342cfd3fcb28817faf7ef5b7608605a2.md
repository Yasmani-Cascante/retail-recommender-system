# DCT F-05 Comportamiento Consistente product_availability — 14 Abr 2026

## Estado: IMPLEMENTADO — Pendiente verificación con test local

---

## 1. Problema identificado

Después de confirmar que F-05 funcionaba técnicamente (`F-05 Stock Alert: Adding stock alert block to prompt` aparecía en logs), se detectó inconsistencia de experiencia:

| Producto | stock_alert | Respuesta |
| --- | --- | --- |
| romper-olivia (S=1, M=1) | critical | Respuesta conversacional ✅ |
| midi-vestido-emma (qty=0 todo) | None | Documento KB estático ❌ |

La condición anterior condicionaba la contextualización a `stock_alert != None`. El problema: el nivel de stock debe modificar el **contenido** de la respuesta, no si el usuario merece una respuesta conversacional.

---

## 2. Principio de diseño

Un usuario preguntando `"¿está disponible?"` en la página de un producto siempre merece una respuesta directa:

- `stock=critical` → "Solo quedan 1-2 tallas S y M"
- `stock=low` → "Quedan pocas unidades en talla L"
- `stock=None, variantes con qty>0` → "Sí, disponible en tallas XS, S, M, L"
- `stock=None, qty=0 todo` → "Lamentablemente está agotado, te muestro alternativas"
- `sin datos de inventario` → Respuesta parcial + oferta de contacto con soporte

---

## 3. Cambios implementados

### Cambio 1: `mcp_conversation_handler.py`

Bloque F-05 actualizado: la condición ahora fuerza contextualización para **todo** `product_availability` cuando hay `product_context` (sin importar el nivel de `stock_alert`).

**Antes:**

```python
if (
    not needs_contextualisation
    and intent_result.sub_intent == "product_availability"
    and _pctx_for_f05
    and _pctx_for_f05.get("stock_alert")  # ← solo si hay alerta
):
```

**Después:**

```python
if (
    not needs_contextualisation
    and intent_result.sub_intent == "product_availability"
    and _pctx_for_f05  # ← siempre si hay contexto de producto
):
```

### Cambio 2: `kb_contextualizer.py` — nueva función `_build_availability_context_block()`

Nueva función que genera contexto de disponibilidad cuando **no** hay `stock_alert` (es decir, complementa `_build_stock_alert_block()`).

Cubre tres estados:

1. **Agotado** (`variant_inventory` tiene keys pero todos qty=0): informa agotamiento, sugiere alternativas
2. **Disponible** (hay variantes con qty>0 y sin alerta): lista tallas disponibles + personalización F-02 (talla del cliente)
3. **Sin datos** (`variant_inventory={}`): respuesta parcial + oferta de contacto

Los dos bloques son **mutuamente excluyentes**: `_build_availability_context_block()` devuelve `""` si hay `stock_alert`.

El `user_prompt` ahora es:

```python
user_prompt = (
    f"{sizing_context}"            # F-02: talla del cliente (si aplica)
    f"{stock_alert_context}"        # F-05: urgencia stock bajo/crítico
    f"{availability_context}"        # F-05: disponibilidad normal/agotado  ← NUEVO
    f"Policy document:..."
    f"Customer question: {query}"
)
```

---

## 4. Flujo completo post-fix

```
Usuario: "¿está disponible?" (en página de cualquier producto)
    ↓
mcp_conversation_handler.py
    ↓
[F-01] product_context = {..., variant_inventory={...}, stock_alert=...}
    ↓
[Intent] INFORMATIONAL / product_availability
    ↓
[F-05 FIX] needs_contextualisation = True
  (siempre que haya product_context, independiente del stock_alert)
    LOG: "F-05 forcing contextualisation for product_availability (stock_alert=none handle=...)"
    ↓
generate_contextual_answer(product_context=...)
    ↓
[kb_contextualizer]
    SI stock_alert: _build_stock_alert_block()    → alerta de urgencia
    SI NO:          _build_availability_context_block() → info de variantes
    (los dos son mutuamente excluyentes)
    ↓
Claude Haiku responde con info real del producto
```

---

## 5. Matrices de comportamiento por estado del producto

| Estado | stock_alert | Bloque activo | Respuesta Claude |
| --- | --- | --- | --- |
| Agotado total (midi-emma) | None | availability (agotado) | "Este producto está agotado. Te muestro alternativas." |
| Disponible normal | None | availability (in_stock) | "Sí, disponible en XS, S, M, L." |
| Stock bajo | low | stock_alert | "Quedan pocas unidades (3-5 uds)." |
| Stock crítico (romper) | critical | stock_alert | "Solo quedan 1 ud en S y 1 en M." |
| Sin datos GraphQL | None | availability (no_data) | "No pude verificar el inventario. Contacta soporte." |

---

## 6. Integración F-02 en availability_context

`_build_availability_context_block()` recibe `size_profile` (opcional) y, cuando hay datos de talla del cliente, personaliza la respuesta:

- Talla cliente disponible: "La talla M está disponible → confírmalo"
- Talla cliente no disponible: "Tu talla M no está → sugiere la más cercana"

Esto integra F-02 y F-05 en un solo bloque de prompt para el caso de disponibilidad con stock normal.

---

## 7. Archivos modificados

| Archivo | Tipo de cambio |
| --- | --- |
| `src/api/core/mcp_conversation_handler.py` | Ampliada condición F-05 (eliminar `and stock_alert`) |
| `src/api/core/kb_contextualizer.py` | Añadida `_build_availability_context_block()`  • activada en `generate_contextual_answer()` |

---

## 8. Test de verificación

**Invalidar cache antes de testear:**

```bash
redis-cli DEL mcp:product:context:midi-vestido-emma-negro:CH
redis-cli DEL mcp:product:context:romper-olivia-verde-rosado:CH
```

**Caso 1 — Producto agotado (midi-vestido-emma-negro):**

Query: `"¿está disponible?"`

Esperado:

```
F-05 forcing contextualisation for product_availability (stock_alert=none handle=midi-vestido-emma-negro)
F-05 availability_context_block built (handle=midi-vestido-emma-negro in_stock=0 out_of_stock=4 no_data=False)
KB Contextualizer: calling claude-... for sub_intent=product_availability
→ Claude: "Lamentablemente este vestido está agotado actualmente..."
```

**Caso 2 — Producto con stock crítico (romper-olivia-verde-rosado):**

Query: `"¿está disponible?"`

Esperado:

```
F-05 forcing contextualisation for product_availability (stock_alert=critical handle=romper-olivia-verde-rosado)
F-05 Stock Alert: Adding stock alert block to prompt (alert=critical...)
KB Contextualizer: calling claude-...
→ Claude: "Solo quedan pocas unidades disponibles en tallas S y M..."
```