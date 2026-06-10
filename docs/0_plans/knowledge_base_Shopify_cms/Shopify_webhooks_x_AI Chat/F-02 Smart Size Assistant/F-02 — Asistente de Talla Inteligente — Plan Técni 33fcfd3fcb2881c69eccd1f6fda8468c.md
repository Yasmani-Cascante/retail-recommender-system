# F-02 — Asistente de Talla Inteligente — Plan Técnico — 11 Abr 2026

## Estado

> 📋 **PLANIFICADO** — Pendiente de implementación
> 

---

## 1. Problema a resolver

El 30-40% de las devoluciones en moda son por talla incorrecta (benchmark Zalando/ASOS). Un usuario que pregunta "¿qué talla debo pedir?" hoy recibe una respuesta genérica de la KB. Con F-02, el sistema:

1. Lee las variantes reales del producto actual (tallas disponibles, descripción)
2. Si el usuario está logueado, consulta su historial de compras para inferir su talla habitual
3. Genera una recomendación personalizada: "Basado en tus compras anteriores, sueles pedir talla M. Este vestido talla igual que los de tu historial."

---

## 2. Prerequisitos

| Prerequisito | Estado | Notas |
| --- | --- | --- |
| F-01 completado | ✅ | `product_context` con variants ya inyectado en `mcp_context` |
| `customer_id` en `widget_context` | ✅ | Ya llega desde Shopify Liquid |
| `CustomerProfileService` | ✅ Parcial | Existe pero solo fetcha LTV tier, no historial de tallas |
| Shopify Admin API autenticada | ✅ | Cliente ya disponible |

F-02 **no requiere webhooks nuevos**. Usa únicamente:

- El `product_context` ya inyectado por F-01 (variants con `selectedOptions`)
- La Customers API (fetch lazy, igual que F-04)

---

## 3. Arquitectura de la solución

### 3.1 Flujo de datos

```
Widget (página de producto)
  → widget_context.product_id = "vestido-azul"
  → widget_context.customer_id = "12345" (si logueado)

mcp_conversation_handler.py
  → F-01: product_context inyectado (ya existe)
      variants: [{title: "XS", available: true}, {title: "S"}, ...]
  → F-02 NEW: size_profile inyectado
      SizeProfileService.get_size_profile(customer_id)
      → historial de tallas del cliente

MCPPersonalizationEngine
  → _build_sizing_context(product_context, size_profile)
  → prompt enriquecido con guía de tallas
```

### 3.2 Componentes nuevos

**A. `SizeProfileService`** — `src/api/mcp_services/size_profile/service.py`

Fetcha el historial de tallas del cliente desde la Customers API de Shopify.

```python
async def get_size_profile(customer_id: str) -> Optional[SizeProfile]:
    """
    Obtiene el perfil de tallas del cliente.
    
    Flujo:
      1. Redis cache check (TTL 24h — el historial de compras no cambia frecuentemente)
      2. Cache miss: Shopify Admin API GET /customers/{id}/orders
         → Extraer variant.selectedOptions donde name normalizados == 'talla'/'size'
      3. Normalizar nombres de opcion (ver seccion 3.3)
      4. Calcular talla mas frecuente por tipo de producto
      5. Guardar en Redis
    """
```

**Modelo de datos:**

```python
@dataclass
class SizeProfile:
    customer_id: str
    size_by_category: Dict[str, str]  # {"VESTIDOS": "M", "TOPS": "S"}
    most_common_size: Optional[str]   # talla mas frecuente global
    orders_analyzed: int
    confidence: float                  # 0-1: cuantos pedidos confirman la talla
    last_updated: float
```

**B. Normalizacion de nombres de opcion** — el riesgo critico del documento

```python
# Shopify permite cualquier nombre en las opciones de variante:
# "Talla", "Size", "Grosse", "Größe", "Talle", "T", "sz"
SIZE_OPTION_NAMES = {
    "talla", "size", "sz", "t",
    "grosse", "taille", "misura"
    # + variantes sin acento
}

def normalize_option_name(name: str) -> bool:
    """True si el nombre de opcion corresponde a talla."""
    n = name.lower().replace('ö','o').replace('ß','ss')
    return n in SIZE_OPTION_NAMES or n.startswith('talla') or n.startswith('size')
```

**C. Enriquecimiento del prompt en `MCPPersonalizationEngine`**

En el metodo que construye el prompt de Claude, anadir un bloque de sizing si hay contexto:

```python
if mcp_context.size_profile and mcp_context.current_product_context:
    sizing_block = _build_sizing_context(
        product_variants=mcp_context.current_product_context.get('variants', []),
        size_profile=mcp_context.size_profile,
    )
    prompt += sizing_block
```

**D. KB update — `sub_intent: product_sizing`**

La KB ya tiene el sub_intent `product_sizing`. El intent detector ya clasifica preguntas de talla como INFORMATIONAL. La mejora es que cuando `size_profile` esta disponible, en lugar de devolver el documento generico de la KB, se usa `kb_contextualizer.py` para generar una respuesta especifica:

```
"Basado en tus compras anteriores, sueles pedir talla M en vestidos. 
 Este vestido tiene las siguientes tallas disponibles: XS, S, M, L.
 La M deberia quedarte bien."
```

---

## 4. Detalle de implementacion por archivo

### Archivos nuevos

| Archivo | Proposito |
| --- | --- |
| `src/api/mcp_services/size_profile/service.py` | SizeProfileService — fetch y cache |
| `src/api/mcp_services/size_profile/__init__.py` | Init del modulo |

### Archivos modificados

| Archivo | Cambio |
| --- | --- |
| `src/api/core/mcp_conversation_handler.py` | Inyeccion de size_profile en mcp_context (similar a F-01 product_context) |
| `src/api/mcp/engines/mcp_personalization_engine.py` | `_build_sizing_context()`  • inyeccion en prompt |
| `src/api/factories/service_factory.py` | `get_size_profile_service()` singleton |
| `src/api/mcp.conversation_state_manager.py` | Campo `size_profile: Optional[SizeProfile]` en `MCPConversationContext` |

---

## 5. Flujo exacto en `mcp_conversation_handler.py`

```python
# Despues del bloque F-01 (product_context inyectado), anadir:

# ── F-02: Lazy fetch del perfil de tallas del cliente ──────────────
# Solo si hay customer_id (usuario logueado) Y hay producto actual
# (el size_profile solo es util si el usuario esta en una pagina de producto).
# Sin producto actual, no hay variantes que comparar.
if customer_id and validated_product_id:
    try:
        from src.api.factories.service_factory import ServiceFactory
        _sps = await ServiceFactory.get_size_profile_service()
        if _sps:
            _size_profile = await _sps.get_size_profile(str(customer_id))
            if _size_profile:
                mcp_context.size_profile = _size_profile
                logger.info(
                    f"F-02 size_profile_injected "
                    f"customer_id={customer_id} "
                    f"most_common={_size_profile.most_common_size} "
                    f"confidence={_size_profile.confidence:.2f}"
                )
    except Exception as _spe:
        logger.warning(f"F-02 size profile fetch failed (graceful): {_spe}")
# ── Fin F-02 ──────────────────────────────────────────────────────
```

---

## 6. Llamada a Shopify para historial de tallas

```python
# GET /admin/api/2025-01/customers/{customer_id}/orders.json
# ?fields=line_items&limit=10&status=paid

# Respuesta relevante:
# order.line_items[].variant.selected_options[]
#   [{"name": "Talla", "value": "M"}]

# Extraer solo opciones que son tallas:
for order in orders:
    for item in order['line_items']:
        variant = item.get('variant', {})
        for option in variant.get('selected_options', []):
            if normalize_option_name(option['name']):
                category = infer_category_from_title(item['title'])
                size_history[category].append(option['value'])
```

---

## 7. Manejo del intent

Cuando el usuario pregunta por talla, el intent detector ya devuelve `INFORMATIONAL / product_sizing`. El flujo actual devuelve el documento de KB generico.

**Con F-02 activo**, la logica en `mcp_conversation_handler.py` para el path INFORMATIONAL debe agregar:

```python
# En el bloque de INFORMATIONAL, antes de llamar kb_obj.get_answer():
if intent_result.sub_intent == 'product_sizing' and mcp_context.size_profile:
    # Usar kb_contextualizer con el size_profile para personalizar
    # la respuesta en lugar de devolver el documento generico.
    personalized_sizing = await generate_sizing_answer(
        query=conversation_query,
        size_profile=mcp_context.size_profile,
        product_variants=mcp_context.current_product_context.get('variants', []),
        language=language,
    )
    if personalized_sizing:
        return {"type": "informational", "answer": personalized_sizing, ...}
```

---

## 8. Estimacion de esfuerzo

| Tarea | Dias |
| --- | --- |
| `SizeProfileService`  • normalizacion de opciones | 2 |
| Inyeccion en `mcp_conversation_handler` (patron F-01) | 0.5 |
| `_build_sizing_context` en personalization engine | 1 |
| Update MCPConversationContext + ServiceFactory | 0.5 |
| `generate_sizing_answer` en kb_contextualizer | 1 |
| Tests + validacion en produccion | 1 |
| **Total** | **6 dias** |

---

## 9. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigacion |
| --- | --- | --- |
| Nombres de opciones de talla no normalizables | Medio | Fallback a respuesta generica de KB si `size_profile.confidence < 0.5` |
| Rate limiting Shopify Admin API | Bajo a volumen actual | Cache Redis 24h; maximo 1 llamada por customer_id por dia |
| Usuario sin pedidos previos | Bajo | `orders_analyzed == 0` → respuesta generica sin inferencia |
| Tallas diferentes por marca | Medio | Agrupar por categoria de producto, no solo talla absoluta |

---

## 10. Ejemplo de respuesta esperada

**Sin F-02 (hoy):**

> "Las tallas disponibles para este producto son XS, S, M, L, XL. Para elegir tu talla correcta, consulta nuestra guía de tallas."
> 

**Con F-02 (usuario logueado, 3 pedidos previos de vestidos en talla M):**

> "Basado en tus compras anteriores, sueles pedir talla **M** en vestidos. Este Vestido de Fiesta Sofía está disponible en: XS, S, **M**, L. La M debería quedarte bien igual que en tus pedidos anteriores."
> 

**Con F-02 (usuario logueado, sin pedidos en esa categoria):**

> "Este vestido está disponible en XS, S, M, L. No tengo historial de tallas tuyas en esta categoría, pero puedo ayudarte con la guía de tallas si me dices tu medida de pecho o cadera."
> 

---

## 11. Continuity prompt para proxima sesion

Al comenzar F-02:

1. Leer `src/api/mcp_services/product_context/service.py` como referencia del patron F-01
2. Leer `src/api/factories/service_factory.py` para entender como anadir `get_size_profile_service()`
3. Verificar que `MCPConversationContext` tiene campo `size_profile` (anadir si no existe)
4. Comenzar por `SizeProfileService` — es el componente sin dependencias internas
5. Usar `get_size_profile_service()` con el mismo patron singleton que `get_product_context_service()`