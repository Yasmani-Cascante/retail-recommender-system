# F-05 — Stock Alerts — Plan Técnico — 13 Abr 2026

## Estado

> 📋 **PLANIFICADO** — Investigación completa. Listo para implementación.
> 

---

## 1. Problema a resolver

Cuando un usuario está en la página de un producto con stock bajo, el sistema conversacional no tiene visibilidad del inventario real. Claude puede recomendar productos sin mencionar que "solo quedan 2 unidades en talla S" — perdiendo la oportunidad de crear urgencia legítima que reduce el abandono de página.

F-05 resuelve esto inyectando datos de inventario por variante en el contexto de producto existente, permitiendo que Claude genere respuestas con urgencia calibrada cuando el stock es bajo.

**Impacto esperado:** Reducción del abandono de página del producto actual en un 10–20% cuando hay stock limitado, sin cambios en la infraestructura conversacional.

---

## 2. Hallazgos clave de la investigación

Estos son los hechos críticos que determinan el diseño de F-05, extraídos de la lectura directa del código.

### 2.1 Lo que ya existe y puede reutilizarse

| Componente | Ubicación | Relevancia para F-05 |
| --- | --- | --- |
| `ProductContextService` | `src/api/mcp_services/product_context/service.py` | **Punto de entrada principal.** F-05 enriquece su dict de retorno añadiendo `variant_inventory`. |
| `get_product_context_by_handle()` | `src/api/integrations/shopify_client.py` | Ya hace 2 fetches (REST + GraphQL). F-05 añade un tercer fetch de inventario en la misma función. |
| Webhook `products/update` | `src/api/routers/webhooks_router.py`  • `shopify_webhook_handler.py` | **Ya implementado.** Invalida cache `mcp:product:context:{handle}:{market_id}`. F-05 hace piggyback automático. |
| Redis cache key | `mcp:product:context:{handle}:{market_id}` TTL 300s | El inventario cacheado se invalida con el mismo mecanismo que el contexto. |
| `mcp_context.current_product_context` | `mcp_conversation_handler.py` | Ya inyectado por F-01. F-05 solo enriquece el dict, no añade campos nuevos al context. |
| `MCPConversationContext` | `src/api/mcp/conversation_state_manager.py` | **No requiere cambios.** El inventario viaja dentro del dict `current_product_context`, no como campo nuevo del dataclass. |
| `ServiceFactory` | `src/api/factories/service_factory.py` | Ya tiene `get_product_context_service()` singleton. **No requiere nuevo singleton.** |

### 2.2 Lo que no existe y hay que construir

| Componente | Descripción |
| --- | --- |
| `get_product_inventory_by_id()` en `ShopifyIntegration` | Nuevo método GraphQL que fetcha `inventoryQuantity` por variante. |
| Bloque F-05 en `kb_contextualizer.py` | `_build_stock_alert_block()` — genera el texto de urgencia si hay variantes con stock ≤ umbral. |
| Constantes de umbral | `LOW_STOCK_THRESHOLD = 5`, `CRITICAL_STOCK_THRESHOLD = 2` en el módulo correcto. |

### 2.3 El `inventory_service.py` existente NO es válido para F-05

`src/api/inventory/inventory_service.py` usa datos **simulados** (`random.randint(0, 50)`) y está marcado como `DEPRECATED`. F-05 ignora este archivo completamente y construye el fetch real desde cero en `ShopifyIntegration`, siguiendo el patrón de `get_product_context_by_handle()`.

### 2.4 Cómo llega `product_id` — caveat crítico

`validated_product_id` en el handler es un **handle string** (ej. `"enterito-trini"`), no un ID numérico. `ProductContextService` ya resuelve el ID numérico internamente y lo guarda en el dict como `context["id"]`. F-05 debe usar `product_context["id"]` (numérico) para el fetch de inventario, nunca el handle directamente.

### 2.5 Estructura del dict `product_context` actual (F-01)

```python
{
    "id":             "9978700071221",   # ID numérico Shopify
    "handle":         "enterito-trini",
    "title":          "Enterito Trini Negro",
    "product_type":   "ENTERITOS CORTOS",
    "tags":           ["fiesta", "verano"],
    "collections":    ["Enteritos", "Fiesta"],
    "vendor":         "AI Shoppings",
    "variants_count": 4,
    # F-05 añade:
    # "variant_inventory": {"XS": 12, "S": 2, "M": 0, "L": 8},
    # "stock_alert":        True,   # True si alguna variante tiene stock <= LOW_STOCK_THRESHOLD
    # "inventory_fetched_at": 1713000000.0
}
```

---

## 3. Decisión de diseño: dónde vive el inventario

Hay dos opciones para pasar el inventario al sistema conversacional:

| Opción | Descripción | Pros | Contras |
| --- | --- | --- | --- |
| **A) Enriquecer `product_context` dict** | Añadir `variant_inventory` al dict que ya devuelve `ProductContextService` | Cero cambios en el dataclass, cero cambios en el router, sin riesgo de regresión | El inventario viaja dentro de `current_product_context`; no es un campo de primer nivel |
| B) Añadir `current_product_inventory` al dataclass `MCPConversationContext` | Campo nuevo en el state manager | Semánticamente más limpio | Requiere cambios en serialización/deserialización del state manager, más riesgo |

**Decisión: Opción A.** El inventario es un atributo del producto, no del estado conversacional. Va dentro del dict `product_context`. La opción B añadiría complejidad sin beneficio real dado que F-05 nunca necesita el inventario desacoplado del producto.

---

## 4. Arquitectura de la solución

```
Widget (página de producto)
  → widget_context.product_id = "enterito-trini"  (handle)
  → widget_context.customer_id = "12345" (opcional)

mcp_conversation_handler.py
  → [F-01] ProductContextService.get_product_context(handle)
       Cache hit  (~1ms)  → dict con variant_inventory ya incluido
       Cache miss (~500ms) → fetch Shopify REST + GraphQL colecciones
                             + GraphQL inventario [NUEVO F-05]
             Guarda dict completo en Redis TTL 5min
  → mcp_context.current_product_context = dict enriquecido

[Path INFORMATIONAL product_sizing o TRANSACTIONAL]
  → kb_contextualizer.generate_contextual_answer() [INFORMATIONAL]
       _build_stock_alert_block() lee variant_inventory
       Si stock_alert=True → añade bloque de urgencia al prompt
  ó
  → MCPPersonalizationEngine [TRANSACTIONAL]
       _build_advanced_personalization_prompt() lee variant_inventory
       Si stock_alert=True → añade bloque de urgencia al prompt

Claude genera respuesta con urgencia calibrada:
  "Solo quedan 2 unidades disponibles en talla S.
   Si es tu talla, te recomendaría no esperar."

Webhook products/update (ya registrado, piggyback automático):
  → invalida mcp:product:context:{handle}:* en Redis
  → próximo request re-fetcha inventario fresco
```

---

## 5. API de Shopify para inventario

### 5.1 Opción seleccionada: GraphQL Admin API

Shopify expone el inventario por variante en GraphQL via el campo `inventoryQuantity` en el nodo `ProductVariant`. Una sola query retorna todas las variantes con sus stocks:

```graphql
query GetProductInventory($id: ID!) {
  product(id: $id) {
    variants(first: 20) {
      nodes {
        title
        availableForSale
        inventoryQuantity
        selectedOptions { name value }
      }
    }
  }
}
```

**Por qué GraphQL y no REST:**

- REST `/variants.json?product_id={id}` devuelve `inventory_quantity` pero requiere un fetch separado. GraphQL permite combinarlo con la query de colecciones en un solo call.
- El campo `inventoryQuantity` en GraphQL Admin está disponible sin scopes adicionales (el token ya tiene `read_products`).
- `availableForSale` cubre el caso donde `inventory_policy="continue"` (el merchant permite vender sin stock).

### 5.2 Combinación con la query de colecciones (optimización clave)

Actualmente `get_product_context_by_handle()` hace:

1. REST: `/products.json?handle={handle}` → título, tipo, tags, variants_count
2. GraphQL: `GetProductCollections` → colecciones del producto

Con F-05, la query de colecciones se **extiende** para incluir variantes e inventario:

```graphql
query GetProductContextEnriched($id: ID!) {
  product(id: $id) {
    collections(first: 5) {
      nodes { title }
    }
    variants(first: 20) {
      nodes {
        title
        availableForSale
        inventoryQuantity
        selectedOptions { name value }
      }
    }
  }
}
```

Esto mantiene el número de fetches a Shopify en **2** (REST + GraphQL), exactamente igual que antes. Sin overhead de latencia adicional.

### 5.3 Normalización del inventario

La respuesta GraphQL devuelve variantes por opción (`title: "M / Negro"`). La función de normalización extrae el nombre de talla:

```python
def _extract_size_from_variant_title(title: str) -> str:
    """
    "M / Negro" → "M"
    "37" → "37"
    "Único" → "ÚNICO"  (talla única)
    """
    if " / " in title:
        return title.split(" / ")[0].strip().upper()
    return title.strip().upper()
```

Resultado: `{"XS": 12, "S": 2, "M": 0, "L": 8}` — dict {talla: cantidad}.

---

## 6. Umbrales de stock y lógica de alerta

```python
# En ProductContextService o como constantes del módulo
LOW_STOCK_THRESHOLD = 5      # 1–5 unidades → alerta de stock bajo
CRITICAL_STOCK_THRESHOLD = 2  # 1–2 unidades → alerta crítica (máxima urgencia)

def _calculate_stock_alert(variant_inventory: Dict[str, int]) -> Optional[str]:
    """
    Determina el nivel de alerta basado en el inventario por variante.
    
    Returns:
        None      → sin alerta (stock normal en todas las variantes)
        "low"     → al menos una variante tiene 3-5 unidades
        "critical" → al menos una variante tiene 1-2 unidades
    """
    min_in_stock = min(
        (qty for qty in variant_inventory.values() if qty > 0),
        default=None
    )
    if min_in_stock is None:
        return None  # Todo agotado — no es "alerta de stock bajo", es otro caso
    if min_in_stock <= CRITICAL_STOCK_THRESHOLD:
        return "critical"
    if min_in_stock <= LOW_STOCK_THRESHOLD:
        return "low"
    return None
```

**Diseño deliberado:** Si todas las variantes tienen stock 0, no se genera alerta de urgencia (el producto está agotado — otro mensaje). La alerta de "stock bajo" solo aplica cuando hay al menos una variante disponible con inventario limitado.

---

## 7. Detalle de implementación por archivo

### Paso 1 — `shopify_client.py`: Extender `get_product_context_by_handle()`

**Archivo:** `src/api/integrations/shopify_client.py`

**Cambio:** Extender la query GraphQL existente para incluir variantes e inventario.

```python
# Query ACTUAL (solo colecciones):
gql_query = """
  query GetProductCollections($id: ID!) {
    product(id: $id) {
      collections(first: 5) { nodes { title } }
    }
  }
"""

# Query NUEVA (colecciones + inventario — mismo número de calls):
gql_query = """
  query GetProductContextEnriched($id: ID!) {
    product(id: $id) {
      collections(first: 5) { nodes { title } }
      variants(first: 20) {
        nodes {
          title
          availableForSale
          inventoryQuantity
          selectedOptions { name value }
        }
      }
    }
  }
"""
```

**Procesamiento del resultado:**

```python
# Extraer inventario de los nodos de variantes
variant_inventory: Dict[str, int] = {}
variants_nodes = (
    gql_data.get("data", {})
    .get("product", {})
    .get("variants", {})
    .get("nodes", [])
)
for v in variants_nodes:
    size = _extract_size_from_variant_title(v.get("title", ""))
    qty = v.get("inventoryQuantity") or 0
    available = v.get("availableForSale", False)
    # Solo incluir si availableForSale O si tiene inventory
    # (availableForSale cubre inventory_policy="continue")
    if available or qty > 0:
        variant_inventory[size] = qty
```

**Dict de retorno enriquecido:**

```python
context = {
    "id":               str(product_id),
    "handle":           handle,
    "title":            product.get("title", ""),
    "product_type":     product.get("product_type", ""),
    "tags":             tags,
    "collections":      collections,
    "vendor":           product.get("vendor", ""),
    "variants_count":   variants_count,
    # F-05: campos nuevos
    "variant_inventory": variant_inventory,          # {"S": 2, "M": 8, "L": 12}
    "stock_alert":       _calculate_stock_alert_level(variant_inventory),  # None | "low" | "critical"
    "inventory_fetched_at": time.time(),
}
```

**Degradación graceful:** Si el campo `inventoryQuantity` no está disponible (ej. scope insuficiente), `variants_nodes` retorna listas vacías. `variant_inventory` queda `{}` y `stock_alert` queda `None`. El chat continúa sin alerta. Cero errores visibles al usuario.

---

### Paso 2 — `kb_contextualizer.py`: Bloque de urgencia

**Archivo:** `src/api/core/kb_contextualizer.py`

**Cambio:** Añadir `_build_stock_alert_block()` y llamarla desde `generate_contextual_answer()` cuando hay alerta activa.

```python
# Constantes
LOW_STOCK_THRESHOLD = 5
CRITICAL_STOCK_THRESHOLD = 2

def _build_stock_alert_block(
    product_context: Dict[str, Any],
    language: str = "es",
) -> str:
    """
    Construye un bloque de contexto de stock para el prompt de Claude.
    Solo se incluye si hay variantes con stock <= LOW_STOCK_THRESHOLD.
    
    Ejemplos de output (ES):
      "ALERTA DE STOCK: Solo quedan 2 unidades en talla S."
      "DISPONIBILIDAD LIMITADA: 3 unidades en S, 1 unidad en XS."
    
    Args:
        product_context: Dict con variant_inventory y stock_alert.
        language: "es" o "en" — controla el idioma del bloque.
    
    Returns:
        String con el bloque de contexto, o "" si no hay alerta.
    """
    stock_alert = product_context.get("stock_alert")
    variant_inventory = product_context.get("variant_inventory", {})
    
    if not stock_alert or not variant_inventory:
        return ""
    
    # Filtrar solo variantes con stock bajo (> 0 pero <= umbral)
    low_stock_variants = {
        size: qty
        for size, qty in variant_inventory.items()
        if 0 < qty <= LOW_STOCK_THRESHOLD
    }
    
    if not low_stock_variants:
        return ""
    
    # Construir lista de variantes con stock bajo
    is_critical = stock_alert == "critical"
    
    if language == "es":
        if len(low_stock_variants) == 1:
            size, qty = next(iter(low_stock_variants.items()))
            unit = "unidad" if qty == 1 else "unidades"
            header = "⚠️ STOCK CRÍTICO" if is_critical else "⚠️ STOCK LIMITADO"
            return (
                f"{header}: Solo {qty} {unit} disponible"
                f"{'s' if qty > 1 else ''} en talla {size}.\n"
                f"Si el usuario pregunta por este producto, menciona la disponibilidad "
                f"limitada de forma natural (sin alarmar).\n"
            )
        else:
            lines = [f"{size}: {qty} ud." for size, qty in sorted(low_stock_variants.items())]
            header = "⚠️ STOCK CRÍTICO EN VARIAS TALLAS" if is_critical else "⚠️ STOCK LIMITADO EN VARIAS TALLAS"
            return (
                f"{header}: {", ".join(lines)}.\n"
                f"Menciona la disponibilidad limitada de forma natural si el usuario "
                f"pregunta por el producto.\n"
            )
    else:  # English
        if len(low_stock_variants) == 1:
            size, qty = next(iter(low_stock_variants.items()))
            unit = "unit" if qty == 1 else "units"
            header = "⚠️ CRITICAL STOCK" if is_critical else "⚠️ LOW STOCK"
            return (
                f"{header}: Only {qty} {unit} left in size {size}.\n"
                f"Naturally mention limited availability if the user asks about this product.\n"
            )
        else:
            lines = [f"{size}: {qty} units" for size, qty in sorted(low_stock_variants.items())]
            header = "⚠️ CRITICAL STOCK" if is_critical else "⚠️ LOW STOCK"
            return (
                f"{header}: Limited sizes — {", ".join(lines)}.\n"
                f"Naturally mention limited availability if the user asks.\n"
            )
```

**Activación en `generate_contextual_answer()`:**

```python
# Después del bloque sizing_context y antes de user_prompt:
stock_alert_context = ""
if product_context and product_context.get("stock_alert"):
    stock_alert_context = _build_stock_alert_block(
        product_context=product_context,
        language=lang_key,
    )
    if stock_alert_context:
        logger.info(
            "⚠️ F-05 Stock Alert: Adding stock alert block to prompt "
            "(alert=%s, variants=%s)",
            product_context["stock_alert"],
            list(product_context.get("variant_inventory", {}).keys()),
        )

# user_prompt actualizado:
user_prompt = (
    f"{sizing_context}"
    f"{stock_alert_context}"   # F-05: bloque de urgencia (vacío si no hay alerta)
    f"Policy document:\n\"\"\"\n{kb_document}\n\"\"\"\n\n"
    f"Customer question: {query}\n\n"
    f"Answer the customer's specific question based only on the document above."
)
```

---

### Paso 3 — `mcp_personalization_engine.py`: Bloque de urgencia en TRANSACTIONAL

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`

**Cambio:** En `_build_advanced_personalization_prompt()`, añadir el bloque de stock alert después del bloque sizing.

```python
# En _build_advanced_personalization_prompt(), después del bloque F-02 sizing:

# ── F-05: Stock Alert ────────────────────────────────────────────────────
# Si el producto actual tiene variantes con stock bajo, añadir contexto
# de urgencia al prompt de Claude para que lo mencione naturalmente.
if (
    hasattr(mcp_context, 'current_product_context')
    and mcp_context.current_product_context
    and mcp_context.current_product_context.get('stock_alert')
):
    from src.api.core.kb_contextualizer import _build_stock_alert_block
    _lang = getattr(mcp_context, 'language', 'es') or 'es'
    stock_alert_block = _build_stock_alert_block(
        product_context=mcp_context.current_product_context,
        language=_lang.split('-')[0].lower(),
    )
    if stock_alert_block:
        prompt_parts.append(stock_alert_block)
        logger.info(
            "F-05 stock_alert_added_to_prompt",
            alert_level=mcp_context.current_product_context['stock_alert'],
            handle=mcp_context.current_product_context.get('handle', '?'),
        )
# ── Fin F-05 ─────────────────────────────────────────────────────────────
```

---

### Paso 4 — `mcp_conversation_handler.py`: Activación condicional F-05

**Archivo:** `src/api/core/mcp_conversation_handler.py`

**Cambio:** Ninguno. F-05 es transparente para el handler. El `product_context` ya se inyecta en el bloque F-01. El inventario viaja dentro del mismo dict. El bloque F-05 en `kb_contextualizer.py` y `mcp_personalization_engine.py` se activa automáticamente si `stock_alert` está presente.

Solo añadir un log de diagnóstico en el bloque F-01 para confirmar que el inventario llegó:

```python
if _product_ctx:
    mcp_context.current_product_context = _product_ctx
    # Log existente F-01
    logger.info(
        f"F-01 product_context_injected "
        f"handle={validated_product_id} ..."
    )
    # F-05: log de diagnóstico (no bloquea nada)
    _inv = _product_ctx.get("variant_inventory", {})
    _alert = _product_ctx.get("stock_alert")
    if _alert:
        logger.info(
            f"F-05 stock_alert_detected "
            f"handle={validated_product_id} "
            f"alert={_alert} "
            f"variants={list(_inv.keys())}"
        )
```

---

## 8. Archivos a crear / modificar

| Archivo | Tipo de cambio | Líneas estimadas | Riesgo |
| --- | --- | --- | --- |
| `src/api/integrations/shopify_client.py` | **MODIFICAR** — extender query GraphQL | ~40 líneas nuevas | Bajo — solo se extiende una query existente |
| `src/api/core/kb_contextualizer.py` | **MODIFICAR** — añadir `_build_stock_alert_block()` | ~60 líneas nuevas | Bajo — función nueva, activación condicional |
| `src/api/mcp/engines/mcp_personalization_engine.py` | **MODIFICAR** — bloque F-05 en prompt builder | ~15 líneas nuevas | Bajo — bloque condicional, sin tocar lógica existente |
| `src/api/core/mcp_conversation_handler.py` | **MODIFICAR** — log diagnóstico F-05 | ~8 líneas nuevas | Mínimo — solo logging |
| `scripts/test_f05_stock_alert.py` | **CREAR** — script de test local | ~40 líneas | N/A |

**Archivos que NO se modifican:**

- `service_factory.py` — no hay nuevo singleton
- `conversation_state_manager.py` — no hay nuevos campos en el dataclass
- `webhooks_router.py` — piggyback automático sobre `products/update`
- `shopify_webhook_handler.py` — ya invalida todo el context cache
- `product_context/service.py` — recibe el dict enriquecido sin cambios

---

## 9. Flujo de invalidación de cache (piggyback automático)

Este es uno de los hallazgos más importantes: **F-05 no requiere registrar ningún webhook nuevo**.

El webhook `products/update` ya está registrado en Shopify y ya invalida `mcp:product:context:{handle}:*` para todos los mercados. Cuando el inventario de un producto cambia en Shopify Admin (que dispara `products/update`), el cache completo del product_context — incluyendo el inventario — se invalida automáticamente. El siguiente request re-fetcha con datos frescos.

```
Shopify Admin (merchant actualiza stock)
  → products/update webhook disparado
  → POST /api/webhooks/shopify/products
  → HMAC validado
  → ACK inmediato
  → BackgroundTask: handle_product_event()
      → ProductContextService.invalidate(handle, market_id) para CL, CH, MX, ES
      → DEL mcp:product:context:enterito-trini:CL
      → DEL mcp:product:context:enterito-trini:CH
      → DEL mcp:product:context:enterito-trini:MX
      → DEL mcp:product:context:enterito-trini:ES
  → Próximo request del chat:
      → Cache miss → fetch Shopify REST + GraphQL (con inventario fresco) → recachea
```

**Latencia de actualización:** < 5 segundos desde el cambio en Shopify Admin hasta que el chat refleja el nuevo inventario (webhook + invalidación + próximo request).

---

## 10. TTL y estrategia de cache

El inventario es más volátil que el título o las colecciones de un producto. Sin embargo, F-05 **no cambia el TTL** de `ProductContextService` (actualmente 300s = 5 min). Razones:

1. En un e-commerce de moda de volumen medio, el inventario rara vez cambia más de una vez por hora durante el horario comercial.
2. El webhook `products/update` garantiza invalidación en tiempo real cuando el merchant actualiza manualmente.
3. Reducir el TTL aumentaría los calls a Shopify sin beneficio proporcional.

Si se necesita TTL más corto para inventario, se puede cachear `variant_inventory` por separado con TTL 60s bajo la clave `mcp:product:inventory:{product_id}`. Esta es una **mejora futura**, no un requisito del MVP.

---

## 11. Ejemplos de respuesta esperada

**Sin F-05 (hoy):**

> "Este enterito está disponible en varias tallas. ¿Hay algo más en lo que pueda ayudarte?"
> 

**Con F-05, stock crítico (1–2 unidades en talla S):**

> "Este enterito está disponible en XS, S, M y L. Te cuento que la talla S solo tiene 1 unidad disponible en este momento — si es tu talla, podría valer la pena no esperar mucho."
> 

**Con F-05, stock bajo (3–5 unidades en talla M):**

> "Está disponible en XS, S, M y L. La talla M tiene pocas unidades (3 disponibles), así que si te interesa esa talla, es mejor actuar pronto."
> 

**Con F-05, todo con buen stock:**

> Respuesta normal sin mención de urgencia. Claude no inventa urgencia falsa.
> 

---

## 12. Manejo de casos edge

| Caso | Comportamiento |
| --- | --- |
| `inventoryQuantity` null en GraphQL | Se omite esa variante del dict. `variant_inventory` puede estar incompleto pero no falla. |
| `inventory_policy = "continue"` (overselling) | `availableForSale=true` con `inventoryQuantity=0`. Se trata como disponible (no agotado), `stock_alert=None`. |
| Todas las variantes agotadas | `min_in_stock=None` → `stock_alert=None`. No se genera alerta de urgencia. |
| Producto sin variantes (producto simple) | `variants_nodes=[]` → `variant_inventory={}` → `stock_alert=None`. |
| GraphQL falla | `variant_inventory={}` → `stock_alert=None`. Degradación graceful, chat continúa. |
| `product_id` no disponible aún | El inventario solo se fetcha cuando `product_id` está resuelto (después del REST fetch). |

---

## 13. Estimación de esfuerzo

| Paso | Tarea | Días |
| --- | --- | --- |
| 1 | Extender `get_product_context_by_handle()` con inventario GraphQL | 1.0 |
| 2 | `_build_stock_alert_block()` en `kb_contextualizer.py` | 0.5 |
| 3 | Bloque F-05 en `mcp_personalization_engine.py` | 0.5 |
| 4 | Log diagnóstico en `mcp_conversation_handler.py` | 0.25 |
| 5 | Script de test local + invalidar cache de desarrollo | 0.5 |
| 6 | Deploy a Cloud Run + smoke test en producción | 0.5 |
| **Total** |  | **~3.25 días** |

---

## 14. Orden de implementación recomendado

1. **Leer el estado actual** de `get_product_context_by_handle()` en `shopify_client.py` antes de editar (el archivo tiene 42KB, leer con `tail`). Verificar la query GraphQL exacta.
2. **Extender la query GraphQL** (Paso 1). Probar localmente con el script de test que retorna el dict completo con `variant_inventory`.
3. **Implementar `_build_stock_alert_block()`** (Paso 2). El bloque solo se activa cuando `stock_alert` está presente — sin riesgo de regresión.
4. **Añadir el bloque en `mcp_personalization_engine.py`** (Paso 3). Leer el archivo antes de editar para ubicar el bloque F-02 y añadir F-05 después.
5. **Log de diagnóstico** en el handler (Paso 4). Trivial.
6. **Invalidar cache** de desarrollo para el producto de prueba antes del primer test.
7. **Deploy y smoke test** con las queries:
    - Navegar a la página de un producto con stock bajo + enviar "¿están disponibles?"
    - Verificar log `F-05 stock_alert_detected` y `F-05 Stock Alert: Adding stock alert block`
    - Verificar que la respuesta de Claude menciona la disponibilidad limitada

---

## 15. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
| --- | --- | --- | --- |
| `inventoryQuantity` requiere scope adicional (`read_inventory`) | Media | Medio | Verificar en Shopify Admin que `read_products` cubre este campo. Si no, añadir `read_inventory` al token. |
| Extender la query GraphQL aumenta el coste de puntos API | Baja | Bajo | Los 20 nodos de variantes añaden ~20 puntos. El límite es 1000/s. Sin impacto práctico. |
| Latencia adicional en la query GraphQL extendida | Baja | Bajo | La query extendida es la misma llamada HTTP — solo más campos en la respuesta. Overhead < 50ms. |
| Claude inventa urgencia cuando no hay alerta | N/A | Alto | El bloque solo se inyecta si `stock_alert` está presente. Si `stock_alert=None`, el prompt no cambia. |
| Merchant usa `inventory_policy="continue"` para todos los productos | Baja | Bajo | `availableForSale=true` con `inventoryQuantity=0` se trata como disponible. No genera alerta. |

---

## 16. Reglas de arquitectura para esta fase

- `shopify_client.py` → usa `logging` estándar (no structlog), mismo que el resto del archivo.
- `kb_contextualizer.py` → pertenece a `src/api/core/` → usa `logging.getLogger()` con f-strings.
- `mcp_personalization_engine.py` → pertenece a `src/api/mcp/engines/` → usa `structlog.get_logger()` con kwargs.
- El inventario **no modifica** el dataclass `MCPConversationContext` — viaja dentro del dict `current_product_context`.
- `_build_stock_alert_block()` se expone como función pública (sin `__`) para que `mcp_personalization_engine.py` pueda importarla directamente desde `kb_contextualizer`.
- El bloque de urgencia usa **tono suave** ("podría valer la pena no esperar"), nunca alarmista ("¡Última unidad!"). El tono lo controla el prompt, no el bloque de contexto.

---

## 17. Continuity prompt para la sesión de implementación

Al comenzar la sesión de implementación de F-05:

1. Leer `src/api/integrations/shopify_client.py` con `tail=150` para ver el método completo `get_product_context_by_handle()` y la query GraphQL actual.
2. Leer `src/api/core/kb_contextualizer.py` con `tail=80` para ver el bloque de sizing context y el user_prompt, y ubicar dónde insertar el stock alert.
3. Leer `src/api/mcp/engines/mcp_personalization_engine.py` — buscar el bloque F-02 sizing para añadir F-05 después.
4. Verificar en Shopify Admin → Apps → API credentials que el scope `read_inventory` está habilitado (o confirmar que `read_products` cubre `inventoryQuantity`).
5. Comenzar por el Paso 1 (shopify_[client.py](http://client.py)) — es el cambio más crítico y el resto depende de él.
6. Invalidar el cache del producto de prueba antes del primer test local:
    
    ```bash
    redis-cli DEL mcp:product:context:enterito-trini:CL
    ```