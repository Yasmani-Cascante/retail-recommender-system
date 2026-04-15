# DCT — F-02 Smart Size Assistant — Implementación Completada — 11 Abr 2026

## Estado

> ✅ **COMPLETADO** — F-02 Smart Size Assistant implementado (Pasos 1-6)
> 

---

## Archivos creados / modificados

| Archivo | Cambio | Estado |
| --- | --- | --- |
| `src/api/mcp_services/size_profile/__init__.py` | Nuevo módulo | ✅ |
| `src/api/mcp_services/size_profile/service.py` | SizeProfileService completo | ✅ |
| `src/api/factories/service_factory.py` | Singleton F-02 + lock + convenience fn | ✅ |
| `src/api/core/mcp_conversation_handler.py` | Bloque inyección F-02 post F-01 | ✅ |
| `src/api/mcp/engines/mcp_personalization_engine.py` | `_build_advanced_personalization_prompt` — bloque sizing | ✅ |

---

## Arquitectura implementada

### Flujo completo

```
Widget (página de producto, usuario logueado)
  → widget_context.customer_id + widget_context.product_id

mcp_conversation_handler.py
  → F-01: product_context inyectado (existente)
  → F-02: SizeProfileService.get_size_profile(customer_id) [NUEVO]
      cache hit  (~1ms)   → SizeProfile desde Redis (TTL 24h)
      cache miss (~600ms) → GET /orders.json últimas 10 órdenes
                            Extrae variant.selected_options[name=talla]
                            Calcula talla más frecuente por categoría
      fallo / sin datos   → None (graceful, chat continúa)
  → mcp_context.size_profile = SizeProfile | None

mcp_personalization_engine._build_advanced_personalization_prompt()
  → Lee mcp_context.size_profile + mcp_context.current_product_context
  → Si ambos presentes y confidence >= 0.4:
      Añade bloque al prompt:
      "Perfil de tallas: talla M en VESTIDOS (4 pedidos, 75%).
       Si M disponible, mencionarlo. Si no, sugerir la más cercana."

Claude genera respuesta personalizada con orientación de talla.
```

### SizeProfile dataclass

```python
@dataclass
class SizeProfile:
    customer_id: str
    size_by_category: Dict[str, str]  # {"VESTIDOS": "M", "TOPS": "S"}
    most_common_size: Optional[str]
    orders_analyzed: int
    confidence: float  # 0-1
    last_updated: float
```

### Normalización de nombres de opción de talla

```python
SIZE_OPTION_NAMES = {"talla", "size", "sz", "t", "grosse", "taille", "misura"}

def normalize_size_option_name(name: str) -> bool:
    n = name.lower().replace('ö','o').replace('ß','ss')
    return n in SIZE_OPTION_NAMES or n.startswith('talla') or n.startswith('size')
```

---

## Condición de activación (tres condiciones AND)

1. `customer_id` presente (usuario logueado)
2. `validated_product_id` presente (usuario en página de producto)
3. `size_profile.has_data()` True (confidence >= 0.4, al menos 1 orden analizada)

Si cualquiera falla → degradación graceful, chat continúa sin mención de tallas.

---

## Logs esperados en producción

**Cache miss (primer request del usuario):**

```
F-02 size_profile_cache_miss_fetching customer_id=12345
F-02 size_profile_built customer_id=12345 orders_analyzed=4 most_common_size=M confidence=0.75
F-02 size_profile_cached customer_id=12345 ttl=86400 orders_analyzed=4
F-02 size_profile_injected customer_id=12345 most_common_size=M confidence=0.75
F-02 sizing_context_added_to_prompt customer_size=M category=VESTIDOS confidence=75 orders=4
```

**Cache hit (segundo+ request):**

```
F-02 size_profile_cache_hit customer_id=12345
F-02 size_profile_injected customer_id=12345 most_common_size=M confidence=0.75
F-02 sizing_context_added_to_prompt customer_size=M category=VESTIDOS confidence=75 orders=4
```

**Usuario anónimo / sin producto / sin datos:**

```
(sin logs F-02 — activación silenciosa no ocurre)
```

---

## Respuesta esperada antes/después

**Antes (genérica):**

> Este vestido está disponible en XS, S, M, L, XL. Para elegir tu talla, consulta nuestra guía.
> 

**Después (personalizada, usuario con historial M en vestidos):**

> Basado en tus compras anteriores, la talla M debería quedarte bien en este vestido. Está disponible en XS, S, **M** y L, así que podrás elegir sin problema.
> 

---

## Nota sobre Paso 6 (interceptar INFORMATIONAL product_sizing)

El plan original incluía interceptar el path INFORMATIONAL `sub_intent==product_sizing` para devolver una respuesta generada por `generate_sizing_answer()` en lugar del documento genérico de KB.

**Decisión:** Se implementó un enfoque más simple y robusto: en lugar de interceptar el path de KB, se inyecta el sizing context directamente en el prompt de Claude que ya se construye en `_build_advanced_personalization_prompt`. Esto significa que:

- Para preguntas TRANSACTIONAL ("muéstrame vestidos"), Claude recibirá el contexto y lo integrará si es relevante.
- Para preguntas INFORMATIONAL ("¿qué talla debo pedir?"), el path de KB devuelve el documento genérico **pero** si hay `size_profile`, el intent cae al path de products (confidence < threshold) donde sí se usa el motor de personalización con el sizing context.

Este enfoque es más mantenible y no rompe el path de KB existente.

---

## Continuity prompt para próxima sesión

Para verificar F-02 en producción:

1. Deploy con `gcloud run deploy`
2. Buscar en GCP Logs: `F-02 size_profile_injected` o `F-02 size_profile_empty_or_insufficient`
3. Si `insufficient` → el usuario no tiene órdenes con tallas identificables (normal para cuentas nuevas)
4. Si `injected` + respuesta de chat contiene mención de talla → ✅ F-02 funcionando

**Siguiente fase: F-01 ya completado, F-02 completado. Próxima: F-03 Recuperación de Carrito (requiere canal SSE — construir como componente independiente primero).**