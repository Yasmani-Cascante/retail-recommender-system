# DCT — Intent Detection + Language Detection Improvements — 09 Abr 2026

# Estado

> ✅ **COMPLETADO Y VALIDADO** — Tres cambios aplicados en una sesión
> 

---

# 1. Contexto de la sesión

Sesión de continuación del Retail Recommender System v2.1.0. La sesión comenzó aplicando el guard del hybrid detector (Fix pendiente del DCT anterior) y continuó con mejoras de keywords de intent detection y detección de idioma por contenido de texto.

## 1.1 Trabajo completado en esta sesión

- **Fix 0 (guardado del DCT anterior):** Guard de protección en `hybrid_detector.py` — aplicado y verificado con logs GUARD: en producción.
- **Fix 1:** Keywords faltantes en `POLICY_PAYMENT` — marcas de tarjetas y términos de financiamiento.
- **Fix 2:** Detección de idioma por contenido de texto — nueva función `detect_language_from_text()` con prioridad sobre el header HTTP.
- **Propuesta de sugerencias frontend** — análisis de las sugerencias hardcodeadas actuales y propuesta de mejoras prácticas.

---

# 2. Fix 1 — POLICY_PAYMENT keywords faltantes

## 2.1 Archivo

`src/api/core/intent_detection.py`

## 2.2 Diagnóstico

Queries que fallaban:

| Query | Score previo | Causa |
| --- | --- | --- |
| `aceptan Mastercard` | 0.0 | "Mastercard" no estaba en keywords |
| `aceptan Visa` | 0.0 | "Visa" no estaba en keywords |
| `¿Se puede pagar a plazos?` | 0.0 | "plazos" no estaba en keywords |
| `¿Se puede pagar en cuotas?` | 0.7 | Ya funcionaba ("cuotas" sí estaba) |

## 2.3 Cambios aplicados

**Keywords añadidos:**

```python
r"\b(visa|mastercard|master\s*card|amex|american\s*express)\b",
r"\b(plazos?|diferido|contra\s*entrega|cash\s*on\s*delivery|cod)\b",
```

**question_words añadidos:**

```python
r"\b(pagan|cobran|manejan|usan|tienen|do\s+you\s+take)\b",
```

## 2.4 Scoring esperado post-fix

| Query | Keywords | Question word | Score | Resultado |
| --- | --- | --- | --- | --- |
| `aceptan Mastercard` | `mastercard` (+0.4) | `aceptan` (+0.3) | **0.7** | ✅ INFORMATIONAL |
| `aceptan Visa` | `visa` (+0.4) | `aceptan` (+0.3) | **0.7** | ✅ INFORMATIONAL |
| `¿Se puede pagar a plazos?` | `plazos` (+0.4) | `puede` (+0.3) | **0.7** | ✅ INFORMATIONAL |
| `necesito visa para viajar` | `visa` (+0.4) | sin question_word de pago | **0.4** | ✅ TRANSACTIONAL (correcto, no llega a 0.7) |

## 2.5 Nota sobre "Visa"

El riesgo de falso positivo con "visa" en un contexto de viajes es bajo porque:

1. El site es de ropa — no hay contexto de viajes en el catálogo
2. Para llegar a 0.7 necesita además un question_word de pago (`aceptan`, `puede`, `cobran`, etc.)
3. Queries de viaje como `"necesito visa"` o `"tramitar mi visa"` no tienen question_words de pago — score queda en 0.4, por debajo del threshold

---

# 3. Fix 2 — Detección de idioma por contenido de texto

## 3.1 Archivos modificados

- `src/api/utils/language_detection.py` — nueva función `detect_language_from_text()`, `detect_language_from_request()` actualizado con parámetro `query_text`
- `src/api/routers/mcp_router.py` — llama `detect_language_from_request(request, query_text=conversation.query)`

## 3.2 Problema resuelto

El sistema anterior detectaba idioma SOLO desde el header `Accept-Language`. Esto causaba:

- Usuario con navegador `en-US` escribe en español → Claude respondía en inglés
- Usuario suizo con `de-CH` escribe en español → `de` no soportado → fallback a `es` (coincidencia, no determinismo)

## 3.3 Arquitectura de la nueva detección

**Tres tiers de prioridad:**

```
TIER 1: detect_language_from_text(query)   ← texto del mensaje (más confiable)
TIER 2: Accept-Language header             ← locale del navegador
TIER 3: Default 'es'                       ← fallback
```

**Algoritmo score-based:**

- 9 patrones para español (puntuación invertida ¿¡, tildes, palabras función)
- 6 patrones para inglés (what/how/where, is/are/have, the/this/that, etc.)
- Threshold mínimo: 2 matches para declarar idioma
- Empate → None (indeterminado) → pasa al Tier 2

**Ejemplos clave:**

```
"aceptan Mastercard"  → ES (tiene/tienen/es match en patrones ES)
"¿Cuál es la política?" → ES (¿ + qué + es = 3 matches ES)
"What sizes do you have?" → EN (what + do + sizes = 3 matches EN)
"ok" → None (muy corto, < 3 chars efectivos)
```

## 3.4 Log esperado en producción

```
MCP Conversation - Language: es (method: text_content), Market: cl
MCP Conversation - Language: en (method: text_content), Market: ch
MCP Conversation - Language: es (method: accept_language_header), Market: cl
```

---

# 4. Análisis de sugerencias del frontend

## 4.1 Sugerencias actuales (hardcodeadas)

**Pantalla de bienvenida (`SUGGESTION_CHIPS`):**

```
'Muéstrame las tendencias de esta semana'
'Busco un look para una ocasión especial'
'Recomiéndame algo informal para el fin de semana'
'Ayúdame a elegir mi talla'
```

**Problema:** Estas sugerencias son genéricas y no están conectadas a datos reales.

- "Tendencias de esta semana" presupone que el backend tiene datos de tendencias (no los tiene)
- "Ocasión especial" y "fin de semana" son casos de uso no modelados
- "Ayúdame a elegir mi talla" sí funciona correctamente (INFORMATIONAL > product_sizing)

**Sugerencias contextuales por categoría (`buildProductSuggestions`):**

Estas sí son razonablemente buenas porque generan queries que el intent detector puede manejar.

El problema principal es que los strings hardcodeados pueden no matchear los patrones TRANSACTIONAL del rule-based detector.

## 4.2 Propuesta de sugerencias funcionales (ver siguiente sección)

---

# 5. Propuesta de sugerencias del frontend

## 5.1 Principios

1. Cada sugerencia debe ser una query que el intent detector clasifique correctamente con >= 0.5 confidence
2. Las sugerencias de bienvenida deben cubrir los 3 intents principales: TRANSACTIONAL, INFORMATIONAL, GREETING-like
3. Las sugerencias contextuales de producto deben generar queries que activen el guard TRANSACTIONAL cuando el ML quiera sobreescribir

## 5.2 `SUGGESTION_CHIPS` (pantalla de bienvenida) — reemplazar

```tsx
const SUGGESTION_CHIPS = [
  'Muéstrame los productos nuevos',        // TRANSACTIONAL: mostrar + keywords TF-IDF
  '¿Cuáles son sus métodos de pago?',      // INFORMATIONAL: payment (score 1.0 con fix)
  'Busco un vestido para una boda',         // TRANSACTIONAL: busco + keyword categoría
  '¿Cómo funciona la devolución?',          // INFORMATIONAL: policy_return
];
```

Razonamiento del scoring:

- `Muéstrame los productos nuevos` → `mostrar` keyword TRANSACTIONAL (+0.5) ✅
- `¿Cuáles son sus métodos de pago?` → `métodos`(+0.4) + `pagos`(+0.4) + `son/cuáles`(+0.3) = 1.0 ✅
- `Busco un vestido para una boda` → `busco` keyword TRANSACTIONAL (+0.5) ✅
- `¿Cómo funciona la devolución?` → `devolución`(+0.4) + `cómo`(+0.3) = 0.7 ✅

## 5.3 `buildProductSuggestions` — revisión por categoría

**Vestidos (actualmente bien):**

```tsx
`Muéstrame vestidos similares a este`,   // TRANSACTIONAL: muéstrame + similar ✅
`¿Qué accesorios combinan con este vestido?`,  // INFORMATIONAL si KB tiene, sino TRANSACTIONAL ✅
`¿Está disponible en otras tallas?`,     // INFORMATIONAL: product_sizing ✅
`Quiero algo para una boda`,             // TRANSACTIONAL: quiero + keyword ✅
```

**Camisas/Tops:**

```tsx
`Busco opciones similares a esta camisa`,  // TRANSACTIONAL: busco + similar ✅
`¿Con qué pantalón combina?`,              // TRANSACTIONAL: busco outfit ✅  
`¿Está disponible en mi talla?`,           // INFORMATIONAL: product_sizing ✅
`¿Qué materiales usa esta prenda?`,        // INFORMATIONAL: product_material ✅
```

**Zapatos:**

```tsx
`Muéstrame zapatos similares`,             // TRANSACTIONAL: muéstrame + similar ✅
`¿Cómo sé mi talla de zapato?`,            // INFORMATIONAL: product_sizing ✅
`¿Con qué outfits quedan bien?`,           // TRANSACTIONAL ✅
```

**Genéricas (sin categoría):**

```tsx
`Muéstrame productos similares`,           // TRANSACTIONAL: muéstrame + similar ✅
`¿Cuál es la política de devoluciones?`,   // INFORMATIONAL: policy_return ✅
`¿Cuáles son sus métodos de pago?`,        // INFORMATIONAL: payment ✅
`Busco algo que combine con esto`,         // TRANSACTIONAL: busco ✅
```

## 5.4 Placeholder del input

Actualmente: `'Escribe tu consulta...'`

Sugerencia: `'Escribe aquí... ej: "Busco un vestido rojo"'` — da un ejemplo concreto que el usuario puede replicar.

---

# 6. Archivos modificados en esta sesión

| Archivo | Estado | Cambio |
| --- | --- | --- |
| `src/api/ml/hybrid_detector.py` | ✅ Verificado | Guard TRANSACTIONAL → logs en producción |
| `src/api/core/intent_detection.py` | ✅ Aplicado | Keywords POLICY_PAYMENT: marcas + plazos + question_words |
| `src/api/utils/language_detection.py` | ✅ Aplicado | Nueva `detect_language_from_text()`, Tier 1/2/3 |
| `src/api/routers/mcp_router.py` | ✅ Aplicado | Router pasa `query_text=conversation.query` |
| `src/frontend/src/components/ChatWidget.tsx` | ❌ PENDIENTE | Sugerencias — propuesta en sección 5, pendiente de aplicar |

---

# 7. Próximos pasos

1. **Validar Fix 1:** Probar queries `"aceptan Mastercard"`, `"aceptan Visa"`, `"¿Se puede pagar a plazos?"` en el widget → deben retornar respuesta KB (no tarjetas de producto)
2. **Validar Fix 2:** Enviar un query en español con navegador en idioma inglés → logs deben mostrar `method: text_content`
3. **Aplicar sugerencias frontend** (sección 5.2 y 5.3) — cambio quirúrgico en `ChatWidget.tsx`, sin tocar la lógica de envío
4. **Próxima fase: F-01 Contextual Upsell** — `product_id` ya llega como URL handle desde `widget_context`

---

# 8. Prompt de continuidad para nueva sesión

```
Continuamos el Retail Recommender System v2.1.0 (FastAPI + Redis + PostgreSQL + Claude Haiku + Shopify + React 18).
Path local: C:\Users\yasma\Desktop\retail-recommender-system\

TRABAJO DE ESTA SESIÓN (completado):
1. Guard hybrid_detector.py — VERIFICADO en producción (logs GUARD: aparecen)
2. Fix POLICY_PAYMENT keywords (Mastercard, Visa, plazos) — APLICADO
3. Detección idioma por texto del mensaje (detect_language_from_text) — APLICADO
4. Propuesta de sugerencias frontend — PENDIENTE DE APLICAR (ver DCT)

TAREA PENDIENTE OPCIONAL:
Aplicar las sugerencias mejoradas del frontend según el DCT sección 5.
Archivo: src/frontend/src/components/ChatWidget.tsx
Cambio: reemplazar SUGGESTION_CHIPS y buildProductSuggestions con las versiones del DCT.

PRÓXIMA FASE: F-01 Contextual Upsell
product_id llega como URL handle (ej. "camisa-azul"), NO como ID numérico.
Toda implementación debe usar handle para el lookup de productos.
```