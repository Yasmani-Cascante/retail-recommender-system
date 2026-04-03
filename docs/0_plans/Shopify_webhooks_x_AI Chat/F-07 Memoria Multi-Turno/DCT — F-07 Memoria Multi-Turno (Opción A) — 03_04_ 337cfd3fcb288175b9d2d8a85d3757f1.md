# DCT — F-07 Memoria Multi-Turno (Opción A) — 03_04_2026

## Objetivo

Mejorar la memoria conversacional del chat: en lugar de concatenar las queries de los últimos 3 turnos en un string plano, generar un historial estructurado que Claude pueda usar para construir respuestas coherentes.

---

## Estado previo (problema)

El código anterior hacía esto:

```python
recent_messages = [turn.user_query.lower() for turn in mcp_context.turns[-3:]]
last_query = " ".join(recent_messages)
```

Claude recibía en el prompt: `Contexto conversacional reciente: 'cinturones quiero algo mas informal muestrame mas'.`

Tres queries pegadas sin estructura. Claude no sabía cuál era el mensaje más reciente, no sabía qué productos se habían mostrado, y no podía construir sobre la conversación de forma coherente.

---

## Cambios aplicados

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`

**Cambio 1 — Generación del historial estructurado:**

```python
# F-07 (Opcion A): Historial estructurado de los ultimos 3 turns.
history_lines = []
for turn in mcp_context.turns[-3:]:
    rec_ids = turn.recommendations_provided
    if rec_ids:
        rec_str = f"{len(rec_ids)} producto(s) mostrado(s)"
    else:
        rec_str = "sin productos (respuesta informacional)"
    history_lines.append(
        f"  Turno {turn.turn_number}: '{turn.user_query}' → {rec_str}"
    )
last_query = "\n".join(history_lines)
```

**Cambio 2 — Etiqueta del prompt:**

```python
# Antes:
f"Contexto conversacional reciente: '{last_query}'.\n"

# Después:
f"Historial conversacional (ultimos 3 turnos):\n{last_query}\n"
```

---

## Ejemplo del prompt generado (después)

```
Historial conversacional (ultimos 3 turnos):
  Turno 1: 'cinturones' → 5 producto(s) mostrado(s)
  Turno 2: 'quiero algo más informal' → 5 producto(s) mostrado(s)
  Turno 3: 'muéstrame más' → 5 producto(s) mostrado(s)
Construir sobre la conversacion sin repetir contexto.
Mantén coherencia a traves de la conversacion con el usuario.
```

Claude ahora sabe: cuántos turnos lleva la conversación, qué pidió el usuario en cada uno, y cuántos productos se mostraron (indicando que el usuario ya vio esos productos y quiere diferentes).

---

## Por qué `ai_response` NO se incluye

La respuesta del asistente de cada turno está disponible en `turn.ai_response` pero no se incluye en el historial del prompt por tres razones:

1. Con Haiku, añadir el texto completo de 3 respuestas previas aumentaría los tokens de input significativamente (~300-600 tokens extra por conversación)
2. La información de qué productos se mostraron ya captura el contexto clave para evitar repetición
3. La Opción B (multi-turn nativo de la API de Anthropic) es el lugar correcto para pasar `ai_response` cuando se implemente en el futuro

---

## Relación con la infraestructura existente

No hay cambios en:

- `MCPConversationContext` — los turns ya se guardaban correctamente
- `ConversationTurn` — estructura sin cambios
- La lógica de Redis — sin cambios
- El flujo del handler — sin cambios

El único cambio es cómo se serializa el historial de turns al construir el prompt para Claude.

---

## Opción B (pendiente)

Usar el array `messages[]` nativo de la API de Anthropic para pasar el historial completo de la conversación (user + assistant alternados). Está acoplado al formato de Anthropic — si se migra a otro proveedor con diferente protocolo requeriría adaptación. La Opción A (este DCT) es agnóstica al proveedor.