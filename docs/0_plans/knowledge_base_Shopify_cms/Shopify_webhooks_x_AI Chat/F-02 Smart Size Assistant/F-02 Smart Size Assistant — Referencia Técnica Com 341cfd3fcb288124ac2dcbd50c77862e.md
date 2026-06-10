# F-02 Smart Size Assistant — Referencia Técnica Completa

## Qué es F-02 y por qué existe

El 30–40% de las devoluciones en moda se producen por talla incorrecta (benchmark Zalando/ASOS). Antes de F-02, cualquier usuario que preguntaba «¿qué talla me recomiendas?» recibía el documento genérico de guía de tallas de la KB, independientemente de si tenía diez compras previas en la tienda. F-02 cierra ese gap: cuando el usuario está logueado, en una página de producto, el sistema consulta su historial de órdenes de Shopify, infiere su perfil de tallas por categoría y lo inyecta como contexto en Claude para que la respuesta sea personalizada.

F-02 opera en **dos paths** del sistema conversacional:

1. **Path INFORMATIONAL** (`sub_intent: product_sizing`): queries directas sobre talla («¿qué talla pido?», «¿cómo sé mi talla?»). El `KB Contextualizer` genera una respuesta personalizada via Claude Haiku usando el historial.
2. **Path TRANSACTIONAL**: cuando el usuario pide productos («muéstrame enteritos similares»), el sizing context se inyecta en el prompt del `MCPPersonalizationEngine` para que Claude lo integre en su respuesta de recomendaciones.

---

## Capacidades que aporta al sistema

- **Recomendación de talla personalizada**: respuesta basada en historial real de compras del cliente, no en parámetros genéricos.
- **Confianza por categoría**: distingue entre tallas de ropa (M, S), zapatos (37, 36) y lencería (B, C) — no las mezcla en un denominador global.
- **Cobertura multilingüe**: normaliza nombres de opción de talla en español, inglés, alemán, francés e italiano («Talla», «Size», «Größe», «Taille», «Misura»).
- **Degradación graceful**: si no hay historial, si Shopify falla, o si el usuario es anónimo, el chat continúa sin mención de tallas. Sin errores visibles para el usuario.
- **Cache inteligente**: el perfil se cachea 24h en Redis para evitar refetch en cada mensaje.

---

## Prerequisitos satisfechos

| Prerequisito | Estado |
| --- | --- |
| F-01 (`product_context` inyectado en `mcp_context`) | ✅ Completo |
| `customer_id` en `widget_context` (Shopify Liquid) | ✅ Completo |
| Shopify Admin API autenticada | ✅ Completo |
| KB con `sub_intent: product_sizing` | ✅ Completo |
| Redis disponible | ✅ Completo |

F-02 **no requiere webhooks nuevos**. Reutiliza la misma infraestructura de fetch lazy de F-01 y F-04.

---

## Archivos involucrados

| Archivo | Rol en F-02 |
| --- | --- |
| `src/api/mcp_services/size_profile/service.py` | `SizeProfileService` — fetch, cache y cálculo del perfil |
| `src/api/mcp_services/size_profile/__init__.py` | Init del módulo |
| `src/api/factories/service_factory.py` | Singleton `get_size_profile_service()` |
| `src/api/core/mcp_conversation_handler.py` | Inyección de `size_profile` en `mcp_context` (bloque F-02 post F-01) |
| `src/api/core/kb_contextualizer.py` | `_build_sizing_context_block()`  • parámetros `size_profile`/`product_context` en `generate_contextual_answer()` |
| `src/api/mcp/engines/mcp_personalization_engine.py` | Bloque sizing en `_build_advanced_personalization_prompt()` |
| `src/api/core/intent_detection.py` | Patterns `product_sizing` — clasificación correcta de queries de talla |
| `src/api/ml/hybrid_detector.py` | Fix `max(rule, ml)` cuando ambos detectores coinciden en intent |
| `scripts/invalidate_size_profile_cache.py` | Utilidad de invalidación de cache Redis |

---

## Cómo funciona: flujo operacional

```
┌─────────────────────────────────────────────────────────────┐
│  WIDGET (página de producto, usuario logueado)               │
│  widget_context.customer_id = "8831066177845"               │
│  widget_context.product_id  = "enterito-trini"              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  mcp_conversation_handler.py                                │
│                                                             │
│  F-01: ProductContextService → mcp_context.product_context  │
│  F-04: CustomerProfileService → mcp_context.customer_profile│
│  F-02: SizeProfileService.get_size_profile(customer_id)     │
│    ├─ Redis HIT  → SizeProfile (TTL 24h, ~1ms)              │
│    └─ Redis MISS → Shopify /orders.json?limit=10 (~600ms)   │
│         → Extrae variant.selected_options[name=talla]       │
│         → Agrupa por categoría (ENTERITOS, ZAPATOS…)        │
│         → Calcula confianza POR CATEGORÍA                   │
│         → Guarda en Redis TTL 24h                           │
│  mcp_context.size_profile = SizeProfile | None              │
└────────────────────────┬────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
     intent=INFORMATIONAL    intent=TRANSACTIONAL
     sub=product_sizing       (ej. "muéstrame enteritos")
              │                     │
              ▼                     ▼
┌─────────────────────┐  ┌──────────────────────────────────┐
│ kb_contextualizer   │  │ MCPPersonalizationEngine         │
│                     │  │ _build_advanced_prompt()         │
│ _build_sizing_      │  │                                  │
│  context_block()    │  │ Bloque sizing inyectado si:      │
│  → Historial del    │  │ • size_profile presente          │
│    cliente en el    │  │ • current_product_context pres.  │
│    prompt de Haiku  │  │ • confidence_by_category >= 0.4  │
│                     │  │                                  │
│ generate_contextual │  │ Claude integra la talla en su    │
│  _answer() con:     │  │ respuesta de recomendaciones     │
│ • size_profile      │  └──────────────────────────────────┘
│ • product_context   │
│ • kb_document       │
└──────────────────────┘
         │
         ▼
"Según tus compras anteriores, en enteritos
sueles pedir talla S (3 órdenes, 100%
confianza). Este modelo está disponible en
tu talla."
```

---

## Modelo de datos: SizeProfile

```python
@dataclass
class SizeProfile:
    customer_id: str
    size_by_category: Dict[str, str]         # {"ENTERITOS": "S", "ZAPATOS": "37"}
    confidence_by_category: Dict[str, float] # {"ENTERITOS": 1.0, "ZAPATOS": 0.833}
    most_common_size: Optional[str]          # "S" (global, solo para logging)
    orders_analyzed: int                     # órdenes con talla identificable
    confidence: float                        # global (DEPRECADO para has_data())
    last_updated: float
```

**Regla crítica de `has_data()`:** evalúa si **al menos una categoría** tiene confianza ≥ 0.4. No usa la confianza global, que es estructuralmente baja en catálogos multi-categoría (mezcla tallas M/37/B en el mismo denominador).

---

## Condición de activación (tres AND)

| Condición | Fuente |
| --- | --- |
| `customer_id` presente | `widget_context` (Shopify Liquid) |
| `validated_product_id` presente | `widget_context` (URL del producto) |
| `size_profile.has_data() == True` | Al menos 1 categoría con conf ≥ 0.4 |

Si cualquiera falla → sin mención de tallas, degradación silenciosa.

---

## Normalización de nombres de opción de talla

Shopify no estandariza el nombre de la opción de variante que corresponde a talla. Puede ser «Talla», «Size», «Größe», «T», «sz», etc. La función `normalize_size_option_name()` resuelve esto:

```python
SIZE_OPTION_NAMES = {
    "talla", "talle", "talles",   # Español
    "size", "sz",                  # Inglés
    "grosse", "grobe",             # Alemán (normalizado sin diéresis)
    "taille",                      # Francés
    "misura",                      # Italiano
    "t",                           # Abreviación
}

def normalize_size_option_name(name: str) -> bool:
    n = name.lower().replace('ö','o').replace('ß','ss').replace('ä','a').replace('ü','u')
    return n in SIZE_OPTION_NAMES or n.startswith('talla') or n.startswith('size')
```

Fallback si `selected_options` está vacío: analiza `variant_title` (ej. «M / Azul» → toma «M» si tiene ≤ 5 chars y no contiene espacios).

---

## Principales problemas y soluciones

### Problema 1: `has_data()` siempre False en catálogos multi-categoría

**Causa:** La confianza global mezcla tallas incomparables en el mismo denominador. Un cliente con 10 órdenes puede tener ENTERITOS en talla S (100% confianza) y ZAPATOS en talla 37 (83% confianza), pero globalmente la talla más frecuente puede ser S en solo 6/16 items = 0.375 < 0.4.

**Solución:** Añadir `confidence_by_category: Dict[str, float]` al dataclass. `has_data()` evalúa si **alguna categoría** tiene confianza ≥ 0.4, ignorando la confianza global. **Justificación:** las tallas de diferentes categorías no son comparables — mezclarlas penaliza incorrectamente a clientes consistentes que compran en varias categorías.

### Problema 2: KB Contextualizer nunca se activaba para product_sizing

**Causa:** `has_specific_entities()` solo se activaba si el texto de la query contenía entidades nombradas (marcas, medidas en cm). Una query como «¿qué talla pido?» no tiene entidades → `needs_contextualisation=False` → KB devolvía documento genérico aunque hubiera historial disponible.

**Solución:** En el handler, la condición se cambió a `needs_contextualisation OR sub_intent == "product_sizing"`. Para sizing, el historial del usuario **es** el contexto específico relevante, aunque no esté en el texto de la query. **Justificación:** el principio del KB Contextualizer es «usar contexto disponible cuando mejora la respuesta» — el historial del usuario es exactamente ese contexto.

### Problema 3: Queries personales de talla clasificadas como TRANSACTIONAL

**Causa:** Las queries de recomendación personal («Que talla me recomiendas?», «¿Cómo sé mi talla?», «cual es mi talla?») solo matcheaban el keyword `talla` (+0.4 pts), sin ningún `question_word` del detector. Score 0.4 < umbral 0.7 → fallback a TRANSACTIONAL.

**Solución:** 6 nuevos `question_words` en `PRODUCT_SIZING` cubriendo patrones personales: `me recomiendas/recomiéndame`, `mi talla/me queda`, `cómo sé/como me/how do I`, `disponible.*talla`, `cual es mi`, `me recomiend/should I order`. **Justificación:** la scoring logic requiere keyword (+0.4) + question_word (+0.3) = 0.7. Los QW existentes solo cubrían patrones de tercera persona («¿qué tallas tienen?»), no de primera persona.

### Problema 4: Hybrid detector degradaba la confianza del rule-based

**Causa:** El threshold del hybrid detector es 0.80 (env `ML_CONFIDENCE_THRESHOLD`). Queries con `rule_confidence=0.70 < 0.80` activaban el ML fallback. Si el ML confirmaba el mismo intent pero con menor confianza (ej. 0.514), el código retornaba `confidence=ml_confidence=0.514`. Luego el handler verificaba `0.514 < 0.70` (su propio threshold) → TRANSACTIONAL.

**Solución:** Cuando ML y rule-based coinciden en el **mismo** intent, usar `max(rule_confidence, ml_confidence)`. Si discrepan, usar `ml_confidence` sin modificar (el ML está haciendo un override real). **Justificación:** si dos detectores independientes concuerdan en el intent, la evidencia combinada debe aumentar la confianza, no reducirla. La confianza del ML refleja su incertidumbre estadística, no necesariamente la incertidumbre del intent — el rule-based ya aportó una señal fuerte con su patrón matcheado.

### Problema 5: Queries con verbos genéricos bloqueadas por GUARD del hybrid

**Causa:** El GUARD de `hybrid_detector.py` protegía los resultados TRANSACTIONAL del rule-based contra overrides del ML. Funcionaba con `matched_patterns != []`. Queries como «Necesito saber mi talla» matcheaban `necesito` (keyword TRANSACTIONAL genérico), tenían `matched_patterns != []`, y el GUARD bloqueaba el ML (que correctamente quería decir INFORMATIONAL 0.779).

**Solución:** Excepción al GUARD para verbos genéricos de una sola palabra (`necesito`, `quiero`, `need`, `want`) cuando `rule_confidence == 0.5` (el mínimo). Con 1 solo match genérico, el ML tiene autoridad para hacer override. **Justificación:** el GUARD existe para proteger patrones específicos (similaridad, similares, muéstrame) — no para verbos de intención genérica que aparecen en cualquier contexto.

---

## Queries de talla soportadas (cobertura actual)

| Query | Path | Con historial | Sin historial |
| --- | --- | --- | --- |
| «¿Qué talla pido?» | INFORMATIONAL | Respuesta personalizada | Guía genérica KB |
| «Que talla me recomiendas?» | INFORMATIONAL | Respuesta personalizada | Guía genérica KB |
| «¿Cómo sé mi talla?» | INFORMATIONAL | Respuesta personalizada | Guía genérica KB |
| «cual es mi talla?» | INFORMATIONAL | Respuesta personalizada | Guía genérica KB |
| «¿Qué tallas tienen?» | INFORMATIONAL | Sizing context + KB | Guía genérica KB |
| «Necesito saber mi talla» | INFORMATIONAL (vía ML) | Respuesta personalizada | Guía genérica KB |
| «Muéstrame enteritos similares» | TRANSACTIONAL | Sizing en prompt Claude | Sin mención |
| «¿Está disponible en otras tallas?» | INFORMATIONAL | Sizing context + KB | Guía genérica KB |
| «¿Me puedes dar las medidas de la talla M?» | INFORMATIONAL | Sizing context + KB | Guía genérica KB |

---

## Logs de referencia

**Flujo exitoso (cache miss → respuesta personalizada):**

```
F-02 size_profile_cache_miss_fetching customer_id=...
F-02 size_profile_built has_data=True confidence_by_category={'ENTERITOS': 1.0, 'ZAPATOS': 0.833}
F-02 size_profile_cached ttl=86400 orders_analyzed=7
F-02 size_profile_injected by_category={'ENTERITOS': 'S(100%)', 'ZAPATOS': '37(83%)'}
Detected INFORMATIONAL: product_sizing (confidence: 0.70)
ML confirmed rule-based (informational, max confidence: rule=0.70 ml=0.76)
✨ F-02 Informational SubIntent: Adding personalized sizing context to prompt
✅ KB Contextualizer: answer generated in 412ms (187 chars)
```

**Cache hit (segundo request del usuario):**

```
F-02 size_profile_cache_hit customer_id=...
F-02 size_profile_injected by_category={...}
```

**Degradación graceful (usuario anónimo):**

```
(sin logs F-02 — bloque F-02 no se ejecuta, customer_id = None)
```

---

## Observaciones y Gaps

**Gap 1 — Variantes del producto no en `product_context`**

`product_context` incluye `product_type`, `title` y `collections`, pero no la lista de variantes disponibles (XS, S, M, L con stock). La respuesta de Claude puede mencionar tallas pero no puede confirmar disponibilidad exacta. Requiere enriquecimiento adicional de `ProductContextService` con Shopify GraphQL.

**Gap 2 — Log cosmético de confianza**

El log `✨ F-02 Informational SubIntent: Adding personalized sizing context to prompt (confidence: 37%)` muestra `size_profile.confidence` (global, 0.375) en lugar de la confianza de la categoría relevante. Claude recibe el dato correcto en el prompt — es solo el mensaje de log.

**Gap 3 — Cache invalidation no automática**

Si un cliente compra y la talla cambia, el cache Redis no se invalida automáticamente (TTL 24h). Cuando se registre el webhook `orders/create` (F-06), se puede añadir invalidación automática via `SizeProfileService.invalidate(customer_id)`.

**Gap 4 — Cobertura de idiomas en normalización**

El conjunto `SIZE_OPTION_NAMES` cubre 6 idiomas pero puede necesitar ampliación para idiomas adicionales o nombres de opción propietarios de merchants específicos.

**Gap 5 — Tallas numéricas sin contexto de categoría**

El fallback de `variant_title` (ej. «M / Azul») asume que el primer segmento es talla. Funciona en el 95%+ de casos, pero puede capturar erróneamente el primer atributo en merchants con convenciones no estándar.

---

## Recomendaciones y mejoras

**Corto plazo (< 1 semana)**

1. Corregir el log cosmético de confianza para que muestre `confidence_by_category` de la categoría del producto actual en lugar de `confidence` global.
2. Añadir test de regresión automático con las 8 queries de la tabla de cobertura para evitar regresiones futuras en el intent detector.

**Medio plazo (1–4 semanas)**

1. Enriquecer `ProductContextService` con las variantes disponibles (stock > 0) desde Shopify GraphQL. Permitirá que la respuesta confirme disponibilidad exacta en la talla recomendada.
2. Registrar webhook `orders/create` para invalidar el cache de size_profile automáticamente cuando llega una nueva orden (actualmente TTL 24h).

**Largo plazo**

1. Cuando se tengan datos de devoluciones o reviews, añadir un tercer bloque de contexto en el prompt: «otros clientes de talla M reportan que este modelo corre grande».

---

## Próximos pasos: F-05 Alertas de Stock Bajo

### Qué es F-05

Cuando el usuario está en la página de un producto con stock bajo, el sistema notifica proactivamente en el chat: «Solo quedan 2 unidades en talla M». Esto crea urgencia y reduce el abandono de página.

### Por qué F-05 ahora

De las funcionalidades pendientes, F-05 es la más viable sin infraestructura nueva:

- No requiere webhooks SSE (a diferencia de F-03 recuperación de carrito)
- Reutiliza `product_context` ya inyectado por F-01 (el `product_id` ya está disponible)
- El cliente Shopify ya autenticado puede consultar inventario
- ROI medible en 48h de activación

### Prerequisitos de F-05

| Prerequisito | Estado |
| --- | --- |
| F-01 `product_context` inyectado | ✅ Completo |
| Shopify Admin API autenticada | ✅ Completo |
| `widget_context.product_id` (handle) | ✅ Completo |
| Webhook `products/update` | ❌ No registrado aún |

### Enfoque técnico F-05

Dos componentes:

**A. Enriquecimiento de `product_context` con inventory data**

Cuando `ProductContextService` fetcha el producto, añadir `variant_inventory` al dict: `{"XS": 12, "S": 2, "M": 0, "L": 8}`. Umbral de stock bajo: ≤ 3 unidades.

**B. Bloque de urgencia en el prompt**

En `MCPPersonalizationEngine` o `kb_contextualizer.py`, si hay variantes con stock bajo (1–3 unidades), añadir al prompt:

```
STOCK ALERT: Solo quedan 2 unidades en talla S.
Si el usuario pregunta por este producto, mencionar disponibilidad limitada.
```

No requiere canal push (SSE) — la información llega en el contexto del mensaje actual del usuario.

**C. Alternativa con webhook `products/update`**

Registrar `products/update` en `shopify_webhook_registry.py` para actualizar una clave Redis `stock_alert:{product_id}:{variant_id}` cuando el inventario cambia. Esto permite que el handler consulte el estado de stock en O(1) sin hit a Shopify en cada request.

### Estimación F-05

| Tarea | Días |
| --- | --- |
| Enriquecimiento de `product_context` con inventory | 1 |
| Bloque de urgencia en prompt | 0.5 |
| Registro webhook `products/update`  • Redis cache | 1 |
| Test + validación | 0.5 |
| **Total** | **3 días** |

### F-05 no es lo mismo que SSE push

F-03 (recuperación de carrito) y F-06 (notificaciones post-compra) requieren un canal SSE para notificar proactivamente al usuario. F-05 en su forma básica **no lo necesita**: la alerta de stock se incluye en la respuesta del turno actual cuando el usuario ya está interactuando. El canal SSE es un componente independiente que se construirá antes de F-03/F-06.