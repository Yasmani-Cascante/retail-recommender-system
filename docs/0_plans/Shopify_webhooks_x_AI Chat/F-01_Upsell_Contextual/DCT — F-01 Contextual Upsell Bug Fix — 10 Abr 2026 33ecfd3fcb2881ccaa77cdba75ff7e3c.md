# DCT — F-01 Contextual Upsell Bug Fix — 10 Abr 2026

# Estado

> ✅ **COMPLETADO** — Dos bugs identificados desde logs de produccion y corregidos
> 

---

# 1. Contexto

Sesion de debugging post-despliegue de F-01 (Contextual Upsell). El usuario reporto que al pedir recomendaciones desde la pagina de producto de unos aretes, el sistema devolvía vestidos. Los logs de produccion (`downloaded-logs-20260410-020937.json`) revelan la causa raiz.

---

# 2. Diagnóstico — evidencia de los logs

El sistema tiene una sesion de prueba larga (`widget_session_1775773823342_fb5cbkshy`) con 15 turns acumulados. En esa sesion, el usuario habia pedido vestidos en turnos anteriores:

- **Turn 7**: `user_query: 'show me some dresses'` → categories: VESTIDOS LARGOS, VESTIDOS CORTOS, VESTIDOS MIDIS
- **Turn 9**: `user_query: 'Muéstrame vestidos similares a este'` → categories: VESTIDOS LARGOS, VESTIDOS CORTOS, VESTIDOS MIDIS

Cuando el usuario navega a la pagina de **aretes** (`type='AROS'`, `collections=['Complementos']`) y pide recomendaciones:

```
F-01 product_context_injected handle=aros-alana-multicolor-fucsia
  type='AROS' collections=['Complementos']

FIX #1: Building user_events from 15 MCP turns
  Historical categories: ['VESTIDOS LARGOS', 'VESTIDOS CORTOS', 'VESTIDOS MIDIS', ...]
  Preferred categories: ['VESTIDOS LARGOS', 'VESTIDOS CORTOS', 'VESTIDOS MIDIS']

→ Sistema recomienda vestidos en pagina de aretes
```

---

# 3. Bugs identificados

## Bug A — Threshold incorrecto para TRANSACTIONAL

El intent threshold de 0.7 fue diseñado para INFORMATIONAL. Para queries de similares (`"Recoméndame productos similares a este"`), el rule-based da confidence 0.50. El GUARD protege el intent como TRANSACTIONAL, pero el threshold rechaza la request con:

```
⚠️ Intent confidence 0.50 below threshold 0.7 - defaulting to products
```

Esto activa el path de diversificacion (con historial) en lugar del path TF-IDF directo.

## Bug B — Contaminacion del historial en FIX #1

El bloque FIX #1 en `mcp_conversation_handler.py` construye `user_events` iterando TODOS los turns del historial y extrayendo categorias de sus `user_query`. Las queries de vestidos del historial dominan los `user_events`, y el `current_product_context` (F-01, que ya tiene el tipo correcto del producto actual) **se inyecta correctamente pero nunca se usa para construir user_events**.

---

# 4. Fixes aplicados

## Fix A — `src/api/core/mcp_conversation_handler.py`

**Cambio:** Usar threshold efectivo de 0.5 para TRANSACTIONAL (en lugar del threshold global de 0.7).

```python
# ANTES
if intent_result.confidence >= settings.intent_confidence_threshold:  # 0.7

# DESPUES
_effective_threshold = (
    0.5
    if intent_result.primary_intent == _IntentType.TRANSACTIONAL
    else settings.intent_confidence_threshold  # 0.7 para INFORMATIONAL
)
if intent_result.confidence >= _effective_threshold:
```

**Efecto:** Las queries TRANSACTIONAL con confidence 0.50 (patron real matcheado, GUARD activo) ahora pasan directamente al path TF-IDF sin caer al path de diversificacion.

## Fix B — `src/api/core/mcp_conversation_handler.py` (FIX #1 v2)

**Cambio:** Cuando `current_product_context` esta disponible (F-01), construir `user_events` desde el producto actual en lugar del historial.

```python
# ANTES: siempre iterar historial
if mcp_context and mcp_context.total_turns > 0:
    for turn in mcp_context.turns:
        inferred_categories = extract_categories_from_query(turn.user_query, ...)
        user_events.append(...)

# DESPUES: producto actual tiene prioridad
_current_ctx = getattr(mcp_context, "current_product_context", None)
if _current_ctx:
    # PATH PRINCIPAL: usar product_type y collections del producto actual
    user_events = [
        {"product_info": {"product_type": col}} for col in _current_ctx["collections"]
    ] + [{"product_info": {"product_type": _current_ctx["product_type"]}}]
elif mcp_context and mcp_context.total_turns > 0:
    # PATH FALLBACK: solo si no hay producto actual, usar historial
    for turn in mcp_context.turns: ...
```

**Efecto:** En la pagina de aretes, `user_events` = `[{type: 'AROS'}, {type: 'Complementos'}]`. El historial de vestidos no contamina las categorias.

---

# 5. Logs esperados post-fix

**Request desde pagina de aretes:**

```
F-01 product_context_injected handle=aros-alana type='AROS' collections=['Complementos']
FIX #1 v2: user_events built from current_product_context
  (type='AROS', collections=['Complementos'])
  -- historial ignorado para evitar contaminacion de categorias
Detected Intent: transactional (confidence: 0.50)
  [threshold efectivo: 0.5 para TRANSACTIONAL]
F-01 TF-IDF product_id resolved: handle='aros-...' → numeric_id='9978476757301'
→ Recomendaciones de AROS / Complementos
```

---

# 6. Archivos modificados

| Archivo | Cambio |
| --- | --- |
| `src/api/core/mcp_conversation_handler.py` | Fix A: threshold efectivo 0.5 para TRANSACTIONAL |
| `src/api/core/mcp_conversation_handler.py` | Fix B: FIX #1 v2 — current_product_context tiene prioridad sobre historial |

---

# 7. Nota sobre el path TF-IDF vs diversificacion

Con Fix A activo, las queries de similares desde pagina de producto (confidence 0.50, TRANSACTIONAL) pasan al path normal de recomendaciones. En ese path, si hay `diversification_needed=True` (sesion larga), el sistema aun puede activar el path de diversificacion, pero ahora Fix B garantiza que los `user_events` reflejen el producto actual.

Si la sesion es nueva (turn 1), el path es TF-IDF directo sin diversificacion, usando `tfidf_product_id` resuelto por F-01. Este es el caso ideal y mas rapido.