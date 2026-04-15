# DCT F-05 Stock Alerts — Diagnóstico y Fix Completo — 13 Abr 2026

# DCT F-05 Stock Alerts — Diagnóstico y Fix Completo — 13 Abr 2026

## Estado: IMPLEMENTADO — Pendiente verificación con test local

---

## 1. Resumen ejecutivo

F-05 Stock Alerts fue implementado en tres archivos. Durante el primer test se descubrieron dos problemas: (1) el producto de prueba inicial estaba completamente agotado por lo que no debía generar alerta (comportamiento correcto), y (2) el flujo INFORMATIONAL nunca llamaba a `generate_contextual_answer()` para `product_availability` porque `has_specific_entities()` devuelve False para queries genéricas como `"¿está disponible?"`. Se añadió un cuarto fix en `mcp_conversation_handler.py` para forzar la contextualización cuando hay `stock_alert` activo.

---

## 2. Diagnóstico detallado

### 2.1 Test con `midi-vestido-emma-negro`

**Resultado:** `variant_inventory={} stock_alert=None`

**Causa:** El producto tiene 4 variantes (XS/S/M/L × NEGRO) con `inventory_quantity=0` en **todas** y `inventory_policy=deny`. Por diseño, `_calculate_stock_alert_level()` no genera alerta para productos completamente agotados — solo para los que tienen **algunas** variantes con stock bajo. Comportamiento correcto.

**Evidencia (Shopify Admin):** Captura muestra `Total inventory across all locations: 0 available`.

### 2.2 Test con `romper-olivia-verde-rosado`

**Resultado:** `variant_inventory={'S': 1, 'M': 1} stock_alert=critical` ✅

Esta fue la confirmación de que el pipeline de datos (shopify_[client.py](http://client.py)) funciona correctamente.

### 2.3 Error en script de diagnóstico

`inventoryManagement` no existe como campo en la API GraphQL 2025-01 de Shopify. Es un campo REST exclusivo (`inventory_management` en REST). El script incluía ese campo por error. Fue corregido.

### 2.4 Sin logs F-05 en el engine (comportamiento esperado)

El intent `product_availability` es INFORMATIONAL → early return desde KB → el engine nunca se invoca. El bloque F-05 del engine solo actúa en el path TRANSACTIONAL. Para `product_availability` la alerta debe venir desde `kb_contextualizer.generate_contextual_answer()`.

### 2.5 Causa raíz del problema principal

En `mcp_conversation_handler.py`, la condición de activación de `generate_contextual_answer()` era:

```python
if needs_contextualisation or intent_result.sub_intent == "product_sizing":
```

`has_specific_entities("está disponible?", "product_availability")` devuelve `False` porque no hay entidades nombradas (ningún carrier, país, fecha específica). Y `product_availability != product_sizing`. Por tanto, `generate_contextual_answer()` nunca se llamaba para este sub_intent, y el bloque F-05 de `kb_contextualizer` era inalcanzable.

---

## 3. Cambios implementados

### Paso 1: `src/api/integrations/shopify_client.py` ✅

- Query GraphQL extendida de `GetProductCollections` a `GetProductContextEnriched`
- Añadidos campos `variants(first: 20)` con `inventoryQuantity`, `availableForSale`, `selectedOptions`
- Procesamiento del inventario usando `_extract_size_from_variant_title()` y `_calculate_stock_alert_level()`
- Dict de retorno enriquecido: `variant_inventory`, `stock_alert`, `inventory_fetched_at`
- Dos funciones helper a nivel de módulo: `_extract_size_from_variant_title()` y `_calculate_stock_alert_level()`
- Constantes exportables: `_LOW_STOCK_THRESHOLD = 5`, `_CRITICAL_STOCK_THRESHOLD = 2`

### Paso 2: `src/api/core/kb_contextualizer.py` ✅

- Función `_build_stock_alert_block(product_context, language)` añadida
- Bilingüe ES/EN, casos 1-variante y multi-variante
- Tono natural y no alarmista
- Activada en `generate_contextual_answer()`: `stock_alert_context` insertado después de `sizing_context`
- Log: `F-05 Stock Alert: Adding stock alert block to prompt (alert=... handle=... variants=[...])`

### Paso 3: `src/api/mcp/engines/mcp_personalization_engine.py` ✅

- Bloque F-05 insertado en `_build_advanced_personalization_prompt()` después del bloque F-02
- Import lazy de `_build_stock_alert_block` desde `kb_contextualizer`
- Log: `F-05 stock_alert_added_to_prompt alert=... handle=...`
- Degradación graceful con `try/except`

### Paso 4 (FIX): `src/api/core/mcp_conversation_handler.py` ✅

**Este fue el fix crítico.** Se añadió un bloque que fuerza `needs_contextualisation=True` cuando:

- `sub_intent == "product_availability"` AND
- `current_product_context.stock_alert` está activo ("low" o "critical")

```python
_pctx_for_f05 = getattr(mcp_context, "current_product_context", None)
if (
    not needs_contextualisation
    and intent_result.sub_intent == "product_availability"
    and _pctx_for_f05
    and _pctx_for_f05.get("stock_alert")
):
    needs_contextualisation = True
    logger.info(
        "F-05 forcing contextualisation for product_availability "
        "(stock_alert=%s handle=%s)",
        _pctx_for_f05["stock_alert"],
        _pctx_for_f05.get("handle", "?"),
    )
```

### Paso 5 (FIX script): `scripts/debug_f05_inventory.py` ✅

- Eliminado campo `inventoryManagement` de la query GraphQL (no existe en API 2025-01)
- Mejorado diagnóstico para distinguir "producto agotado" de "problema de configuración"
- Añadida la secuencia de logs esperada cuando F-05 funciona

---

## 4. Flujo completo F-05 (post-fix)

```
Usuario: "¿está disponible?"
    ↓
mcp_conversation_handler.py
    ↓
[F-01] get_product_context_by_handle("romper-olivia-verde-rosado")
    → GraphQL: variant_inventory={'S': 1, 'M': 1}, stock_alert=critical
    → product_context inyectado en mcp_context
    ↓
[intent detection]
    → INFORMATIONAL / product_availability (conf=0.77)
    ↓
[F-05 FIX] needs_contextualisation = True  (stock_alert=critical, forzado)
    LOG: "F-05 forcing contextualisation for product_availability"
    ↓
generate_contextual_answer() llamado con product_context
    ↓
[kb_contextualizer]
    _build_stock_alert_block() → bloque de urgencia para S y M
    LOG: "F-05 Stock Alert: Adding stock alert block to prompt"
    ↓
Claude Haiku responde mencionando disponibilidad limitada naturalmente
```

---

## 5. Logs esperados en el test de verificación

```
[get_product_context_by_handle] Collections+inventory resolved via GraphQL
  product_id=... collections=[...] variant_inventory={'S': 1, 'M': 1} stock_alert=critical

F-01 product_context_injected handle=romper-olivia-verde-rosado ...

Detected Intent: IntentType.INFORMATIONAL (confidence: 0.77)

F-05 forcing contextualisation for product_availability
  (stock_alert=critical handle=romper-olivia-verde-rosado)

F-05 Stock Alert: Adding stock alert block to prompt
  (alert=critical handle=romper-olivia-verde-rosado variants=['S', 'M'])

KB Contextualizer: calling claude-3-haiku-... for sub_intent=product_availability
KB Contextualizer: answer generated in ~XXXms
```

---

## 6. Producto de test recomendado

**`romper-olivia-verde-rosado`** (product_id=9978854834485)

- S: 1 unidad, M: 1 unidad, XS: 0, L: 0
- stock_alert=critical ✅
- Colecciones: Enteritos, Fiesta

**Invalida cache antes de testear:**

```bash
# Desde la shell de la app o redis-cli
redis-cli DEL mcp:product:context:romper-olivia-verde-rosado:CH
```

**Query de test:** `"¿está disponible?"` con `product_id=romper-olivia-verde-rosado` en el widget context.

---

## 7. Arquitectura de logging

| Archivo | Módulo de logging | Convención |
| --- | --- | --- |
| `shopify_client.py` | `logging.getLogger(__name__)` | f-strings |
| `kb_contextualizer.py` | `logging.getLogger(__name__)` | f-strings o `%s` |
| `mcp_conversation_handler.py` | `logging.getLogger(__name__)` | f-strings |
| `mcp_personalization_engine.py` | `logging.getLogger(__name__)` | f-strings |

---

## 8. Regla de negocio importante

**F-05 NO genera alerta para productos completamente agotados** (qty=0 en todas las variantes). Solo genera alerta cuando:

- Al menos una variante tiene stock entre 1-5 (`low`) o 1-2 (`critical`)
- La lógica usa el **mínimo de las variantes con stock positivo**, no el promedio

Esto es intencional: un producto completamente agotado debe comunicarse de otra manera, no como "quedan pocas unidades".

---

## 9. Deuda técnica y próximos pasos

- **Webhook piggyback:** El webhook `products/update` ya invalida `mcp:product:context:{handle}:*` — F-05 se beneficia automáticamente sin webhooks nuevos.
- **Cache TTL de product_context:** Actualmente 300s (5 min). El inventario puede cambiar más rápido. Evaluar reducir a 60s para F-05 (trade-off: más requests a Shopify).
- **Próxima feature:** F-01 Contextual Upsell (ya en progreso). `product_id` llega como handle string.