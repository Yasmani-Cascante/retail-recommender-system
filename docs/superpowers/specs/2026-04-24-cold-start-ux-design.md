# Cold Start UX — Design Spec

**Date:** 2026-04-24  
**Branch:** feature/visual_search  
**Status:** Approved

---

## Problem

The system is deployed on Google Cloud Run and scales to zero after a period of inactivity. When a user returns to the chat after the service has shut down, their next message triggers a cold start (20–30s warm-up). Currently the frontend has no awareness of this — the user sees a frozen or slow interface with no explanation.

---

## Solution Overview

**Approach:** Redis Flag + Frontend Polling (30s interval)

During SHUTDOWN, the backend writes a `service:shutdown_at` timestamp to Redis. The frontend polls `/health` every 30 seconds while the chat is open with an active conversation. When the flag is detected (or the request fails), context-appropriate UI is shown.

A 15-minute inactivity timer runs independently as a preventive warning, matching the Zalando UX pattern.

---

## Detection Mechanism

| Trigger | Source | Action |
|---|---|---|
| `service:shutdown_at` flag in Redis | Backend SHUTDOWN phase | Poll picks it up within 30s |
| `/health` request fails (503/timeout) | Network | Treated same as shutdown flag |
| User opens chat with existing `session_id` | Frontend on `isOpen` | Single health check → warm-up trigger |
| 15 min user inactivity (chat open + messages) | Frontend timer | Inline warning message |

---

## Three Cases

### Case 1 — User opens chat (no messages in React state)

1. User clicks chat bubble → `isOpen = true`
2. Frontend fires `GET /health` immediately (this request IS the Cloud Run warm-up trigger)
3. **Spinner only appears after 1.5s** — if health responds faster (service warm), no spinner is shown to avoid flicker on normal opens
4. Spinner text varies by context:
   - `session_id` in localStorage: "Despertando el asistente… Tu sesión anterior está guardada."
   - No prior session: "Iniciando el asistente…"
5. Input is disabled only while spinner is visible
6. When `/health` responds `status: healthy` → spinner disappears, chat is ready normally
7. Polling (30s interval) starts AFTER the initial health check completes to avoid racing

**Header dot color:** yellow (warming, only if spinner shown) → green (ready)

### Case 2 — Chat open with active conversation (`hasUserMessages === true`)

**2a. Preventive: 15-minute inactivity warning**

- Timer resets on every user interaction (message sent, scroll, click)
- At 15 min: inline amber warning appears in the message list:
  > *"¿Sigues ahí? El chat entrará en reposo si no hay actividad en los próximos 5 minutos."*
- If user sends a message, warning disappears and timer resets
- No buttons — purely informational

**2b. Reactive: Shutdown detected (poll or request failure)**

- Poll runs every 30s while `isOpen && hasUserMessages`
- When `shutdown_at !== null` in `/health` response OR request fails:
  - Previous bubbles visually faded (inactive gray)
  - Divider: "mensajes anteriores inactivos"
  - Inline service-down card appears with:
    - Header: 💤 "El asistente ha entrado en reposo"
    - Body: "Tu conversación está guardada. Puedes retomar donde lo dejaste o empezar una nueva conversación."
    - **[Let's continue]** (primary, black)
    - **[Start a new chat]** (secondary, outlined)
    - **[Close conversation]** (ghost, gray)
  - Input is disabled until user chooses

**Header dot color:** red

**Button behavior:**

| Button | Action |
|---|---|
| Let's continue | Call `GET /v1/mcp/session/{session_id}/recap` → show collapsed dropdown → trigger health check as warm-up → re-enable input when ready |
| Start a new chat | Clear `localStorage` session keys → reset React state → show welcome screen |
| Close conversation | `setIsOpen(false)` |

### Case 3 — Chat open on Welcome Screen (no messages)

- Poll also runs every 30s when `isOpen && !hasUserMessages`
- When shutdown detected → `setIsOpen(false)` silently
- Next time user opens the chat → Case 1 applies (health check warm-up)
- No UI shown — less disruptive since there's no conversation to preserve

---

## "Let's Continue" Flow (Post-click)

1. Frontend calls `GET /v1/mcp/session/{session_id}/recap`
2. Previous bubbles remain faded
3. Divider: "reanudando conversación"
4. Collapsed dropdown: "📋 Ver resumen de conversación anterior" (expandable, hidden by default)
   - Expands to show last 2 turns (user query + AI answer) from Redis
5. Inline loading row: spinner + "Resumiendo conversación…"
6. Input remains disabled
7. Frontend polls `/health` until `status: healthy`
8. When ready: spinner disappears, input re-enabled, user continues normally with the same `session_id`

---

## Backend Changes

### B1 — Write shutdown flag (SHUTDOWN phase)
**File:** `src/api/main_unified_redis.py` ~line 1580

Write BEFORE `ServiceFactory.shutdown_all_services()` closes Redis connections:

```python
redis_service = await ServiceFactory.get_redis_service()
await redis_service.set("service:shutdown_at", str(int(time.time())), ex=3600)
```

- TTL: 3600s (1 hour) — auto-expires if service restarts, no manual cleanup needed

### B2 — Enhance `/health` endpoint
**File:** `src/api/main_unified_redis.py` line 1742

Add `shutdown_at` field to the existing healthy response:

```python
# Inside the startup_complete branch:
try:
    redis_client = (await ServiceFactory.get_redis_service()).client
    raw = await redis_client.get("service:shutdown_at")
    shutdown_at = int(raw) if raw else None
except Exception:
    shutdown_at = None

return {
    ...existing fields...,
    "shutdown_at": shutdown_at,
}
```

Frontend interprets `shutdown_at != null` as "service is shutting down or recently shut down."

### B3 — New session recap endpoint
**File:** `src/api/routers/mcp_router.py` (new route)

```
GET /v1/mcp/session/{session_id}/recap
Authorization: X-API-Key header
```

- Reads `conversation_session:{session_id}` from Redis
- Returns last 2 turns (user + assistant) in minimal format
- Returns 404 if session not found or expired

Response schema:
```json
{
  "session_id": "widget_session_xxx",
  "turns": [
    {"role": "user", "content": "Busco vestidos para una boda"},
    {"role": "assistant", "content": "Te recomendé estos 3 modelos…"}
  ]
}
```

Redis key: `conversation_session:{session_id}` (existing, 24h TTL)

---

## Frontend Changes

### New state in `ChatWidget.tsx`

```typescript
type ServiceStatus = 'unknown' | 'healthy' | 'warming' | 'down';
type ColdStartPhase = 'idle' | 'warming' | 'resuming';

// New state:
const [serviceStatus, setServiceStatus] = useState<ServiceStatus>('unknown');
const [coldStartPhase, setColdStartPhase] = useState<ColdStartPhase>('idle');
const [sessionRecap, setSessionRecap] = useState<RecapTurn[] | null>(null);
const lastInteractionRef = useRef<number>(Date.now());
```

### New effects in `ChatWidget.tsx`

1. **On `isOpen` → health check** (Case 1)
   - Fires once when `isOpen` transitions to `true`
   - After 1.5s with no response: sets `serviceStatus = 'warming'` (shows spinner)
   - Sets `serviceStatus = 'healthy'` on success
   - Starts polling interval only after this check completes

2. **Polling effect** (Cases 2 & 3)
   - Starts after initial health check completes (no race condition)
   - Runs every 30s while `isOpen`
   - Reads `shutdown_at` from health response
   - On `shutdown_at !== null` OR request failure → `setServiceStatus('down')`
   - Cleans up interval on `isOpen = false`

3. **Inactivity timer** (Case 2a warning)
   - Tracks `lastInteractionRef` on message send / scroll
   - At 15 min: injects warning message into message list
   - Resets when user sends a message

### New methods in `api.ts`

```typescript
async checkHealth(): Promise<{ status: string; shutdown_at: number | null }>

async getSessionRecap(sessionId: string): Promise<{ turns: RecapTurn[] }>
```

### UI rendering logic

- `serviceStatus === 'warming' && !hasUserMessages` → Case 1 spinner overlay
- `serviceStatus === 'down' && hasUserMessages` → Case 2b card inline
- `serviceStatus === 'down' && !hasUserMessages` → `setIsOpen(false)` (Case 3)
- `coldStartPhase === 'resuming'` → post-"Let's continue" state

### CSS changes (`ChatWidget.module.css`)

New classes needed:
- `.bubbleInactive` — gray faded bubble style
- `.serviceDownCard` — inline shutdown card
- `.inactivityWarning` — amber warning bubble
- `.recapDropdown` / `.recapDropdownBody` — collapsible recap
- `.resumingRow` — spinner + "Resumiendo conversación…" row

---

## Files Changed

| File | Type of change |
|---|---|
| `src/api/main_unified_redis.py` | Add shutdown flag write + enhance `/health` response |
| `src/api/routers/mcp_router.py` | Add `GET /v1/mcp/session/{session_id}/recap` endpoint |
| `src/frontend/src/services/api.ts` | Add `checkHealth()` + `getSessionRecap()` methods |
| `src/frontend/src/components/ChatWidget.tsx` | New state, effects, rendering logic |
| `src/frontend/src/components/ChatWidget.module.css` | New CSS classes for cold start UI states |

---

## Out of Scope

- WebSocket or SSE infrastructure
- AI-generated recap (replaced by C-lite: last 2 turns from Redis)
- Push notifications when service recovers
- Persisting React message state to localStorage (messages live in React state only)
