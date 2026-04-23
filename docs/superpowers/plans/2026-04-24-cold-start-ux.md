# Cold Start UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect Google Cloud Run cold starts and show context-appropriate UI in the chat widget — spinner on open, inline shutdown card with 3 buttons when service goes to sleep, 15-min inactivity warning.

**Architecture:** Backend writes `service:shutdown_at` to Redis during SHUTDOWN; frontend polls `/health` every 30s while chat is open and uses the flag to drive 3 distinct UI cases. Session recap (last 2 turns) is fetched from Redis on "Let's continue" and shown in a collapsed dropdown.

**Tech Stack:** FastAPI (Python), aioredis, React 18 + TypeScript, CSS Modules, Vite

**Spec:** `docs/superpowers/specs/2026-04-24-cold-start-ux-design.md`

---

## File Map

| File | Change |
|---|---|
| `src/api/main_unified_redis.py` | Add `_write_shutdown_flag()` + `_clear_shutdown_flag()` helpers; integrate into lifespan; add `shutdown_at` to `/health` |
| `src/api/routers/mcp_router.py` | Add `GET /v1/mcp/session/{session_id}/recap` endpoint |
| `src/frontend/src/types/widget.ts` | Add `RecapTurn` + `ServiceStatus` types |
| `src/frontend/src/services/api.ts` | Add `checkHealth()`, `getSessionRecap()`, `resetSession()` |
| `src/frontend/src/components/ChatWidget.tsx` | New state, 3 useEffects, button handlers, conditional rendering |
| `src/frontend/src/components/ChatWidget.module.css` | New CSS classes for cold start UI states |
| `tests/unit/test_cold_start_shutdown_flag.py` | Unit tests for flag helpers |
| `tests/unit/test_cold_start_health_endpoint.py` | Unit tests for `/health` shutdown_at field |
| `tests/unit/test_cold_start_recap_endpoint.py` | Unit tests for recap endpoint |

---

## Task 1: Backend — Shutdown flag helper functions

**Files:**
- Modify: `src/api/main_unified_redis.py`
- Create: `tests/unit/test_cold_start_shutdown_flag.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cold_start_shutdown_flag.py`:

```python
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.unit
@pytest.mark.asyncio
async def test_write_shutdown_flag_sets_redis_key_with_ttl():
    mock_client = AsyncMock()
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch(
        'src.api.factories.service_factory.ServiceFactory.get_redis_service',
        return_value=mock_rs,
    ):
        from src.api.main_unified_redis import _write_shutdown_flag
        await _write_shutdown_flag()

    mock_client.set.assert_called_once()
    args, kwargs = mock_client.set.call_args
    assert args[0] == "service:shutdown_at"
    assert int(args[1]) == pytest.approx(int(time.time()), abs=2)
    assert kwargs.get("ex") == 3600


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clear_shutdown_flag_deletes_redis_key():
    mock_client = AsyncMock()
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch(
        'src.api.factories.service_factory.ServiceFactory.get_redis_service',
        return_value=mock_rs,
    ):
        from src.api.main_unified_redis import _clear_shutdown_flag
        await _clear_shutdown_flag()

    mock_client.delete.assert_called_once_with("service:shutdown_at")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_write_shutdown_flag_does_not_raise_on_redis_error():
    mock_rs = MagicMock()
    mock_rs._client.set.side_effect = Exception("Redis connection lost")

    with patch(
        'src.api.factories.service_factory.ServiceFactory.get_redis_service',
        return_value=mock_rs,
    ):
        from src.api.main_unified_redis import _write_shutdown_flag
        await _write_shutdown_flag()  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_cold_start_shutdown_flag.py -v
```

Expected: `ImportError` or `AttributeError` — functions don't exist yet.

- [ ] **Step 3: Add helper functions to main_unified_redis.py**

In `src/api/main_unified_redis.py`, add these two functions right after the imports block (before the `@asynccontextmanager` lifespan function, around line 180):

```python
async def _write_shutdown_flag() -> None:
    """Write service:shutdown_at timestamp to Redis during SHUTDOWN phase."""
    try:
        rs = await ServiceFactory.get_redis_service()
        await rs._client.set("service:shutdown_at", str(int(time.time())), ex=3600)
        logger.info("✅ Cold-start flag: service:shutdown_at written to Redis (TTL 1h)")
    except Exception as e:
        logger.warning(f"⚠️ Could not write shutdown flag to Redis: {e}")


async def _clear_shutdown_flag() -> None:
    """Delete service:shutdown_at from Redis on successful startup."""
    try:
        rs = await ServiceFactory.get_redis_service()
        await rs._client.delete("service:shutdown_at")
        logger.info("✅ Cold-start flag: service:shutdown_at cleared from Redis")
    except Exception as e:
        logger.warning(f"⚠️ Could not clear shutdown flag from Redis: {e}")
```

- [ ] **Step 4: Call `_clear_shutdown_flag()` at end of STARTUP phase**

In `main_unified_redis.py`, right after line 1564 (`startup_complete = True`):

```python
    startup_complete = True
    startup_complete_event.set()
    # Clear any shutdown flag left from previous instance
    await _clear_shutdown_flag()
    logger.info("✅ STARTUP PHASE COMPLETE - Server is ready to accept requests on port 8080")
```

- [ ] **Step 5: Call `_write_shutdown_flag()` at start of SHUTDOWN phase**

In `main_unified_redis.py`, right after line 1579 (`logger.info("🔄 Shutting down...")`):

```python
    logger.info("🔄 Shutting down Enterprise Retail Recommender System")
    # Signal frontend pollers that service is shutting down
    await _write_shutdown_flag()
    
    try:
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/unit/test_cold_start_shutdown_flag.py -v
```

Expected: 3 PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/api/main_unified_redis.py tests/unit/test_cold_start_shutdown_flag.py
git commit -m "feat: add shutdown flag helpers for cold start detection"
```

---

## Task 2: Backend — Enhance /health endpoint with shutdown_at

**Files:**
- Modify: `src/api/main_unified_redis.py` (line ~1742)
- Create: `tests/unit/test_cold_start_health_endpoint.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cold_start_health_endpoint.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_returns_shutdown_at_none_when_no_flag():
    mock_client = AsyncMock()
    mock_client.get.return_value = None  # no flag

    with patch('src.api.main_unified_redis.redis_client', mock_client), \
         patch('src.api.main_unified_redis.startup_complete', True):
        from src.api.main_unified_redis import enterprise_health_check
        result = await enterprise_health_check()

    assert result.get("shutdown_at") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_returns_shutdown_at_timestamp_when_flag_set():
    mock_client = AsyncMock()
    mock_client.get.return_value = b"1745500000"  # Unix timestamp as bytes

    with patch('src.api.main_unified_redis.redis_client', mock_client), \
         patch('src.api.main_unified_redis.startup_complete', True):
        from src.api.main_unified_redis import enterprise_health_check
        result = await enterprise_health_check()

    assert result.get("shutdown_at") == 1745500000


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_returns_shutdown_at_none_when_redis_unavailable():
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("connection refused")

    with patch('src.api.main_unified_redis.redis_client', mock_client), \
         patch('src.api.main_unified_redis.startup_complete', True):
        from src.api.main_unified_redis import enterprise_health_check
        result = await enterprise_health_check()

    assert result.get("shutdown_at") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_cold_start_health_endpoint.py -v
```

Expected: FAIL — `shutdown_at` key not present in response.

- [ ] **Step 3: Modify enterprise_health_check() in main_unified_redis.py**

Replace the `startup_complete` branch (lines 1753–1763) with:

```python
        if startup_complete:
            shutdown_at = None
            if redis_client:
                try:
                    raw = await redis_client.get("service:shutdown_at")
                    shutdown_at = int(raw) if raw else None
                except Exception:
                    pass

            return {
                "timestamp": time.time(),
                "service": "enterprise_retail_recommender",
                "version": "2.1.0-FIXED",
                "status": "healthy",
                "startup_phase": "complete",
                "redis_status": "initializing" if not redis_initialized and redis_error is None else ("ready" if redis_initialized else "failed"),
                "redis_error": redis_error,
                "lifespan_pattern": "modern_contextmanager",
                "shutdown_at": shutdown_at,
            }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_cold_start_health_endpoint.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/api/main_unified_redis.py tests/unit/test_cold_start_health_endpoint.py
git commit -m "feat: add shutdown_at to /health endpoint response"
```

---

## Task 3: Backend — Session recap endpoint

**Files:**
- Modify: `src/api/routers/mcp_router.py`
- Create: `tests/unit/test_cold_start_recap_endpoint.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cold_start_recap_endpoint.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


SAMPLE_SESSION_JSON = json.dumps({
    "session_id": "widget_session_test_123",
    "conversation_history": [
        {"role": "user", "content": "Busco vestidos para una boda"},
        {"role": "assistant", "content": "Te recomiendo estos modelos"},
        {"role": "user", "content": "En color blanco"},
        {"role": "assistant", "content": "Aquí tienes opciones en blanco"},
    ]
})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recap_returns_last_two_messages_from_session():
    mock_client = AsyncMock()
    mock_client.get.return_value = SAMPLE_SESSION_JSON.encode()
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch(
        'src.api.factories.service_factory.ServiceFactory.get_redis_service',
        return_value=mock_rs,
    ):
        from src.api.routers.mcp_router import get_session_recap
        result = await get_session_recap("widget_session_test_123")

    assert result["session_id"] == "widget_session_test_123"
    assert len(result["turns"]) == 2
    assert result["turns"][0] == {"role": "user", "content": "En color blanco"}
    assert result["turns"][1] == {"role": "assistant", "content": "Aquí tienes opciones en blanco"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recap_returns_all_turns_when_session_has_only_one_exchange():
    session = json.dumps({
        "session_id": "widget_session_short",
        "conversation_history": [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿En qué puedo ayudarte?"},
        ]
    })
    mock_client = AsyncMock()
    mock_client.get.return_value = session.encode()
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch(
        'src.api.factories.service_factory.ServiceFactory.get_redis_service',
        return_value=mock_rs,
    ):
        from src.api.routers.mcp_router import get_session_recap
        result = await get_session_recap("widget_session_short")

    assert len(result["turns"]) == 2
    assert result["turns"][0]["role"] == "user"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recap_raises_404_when_session_not_found():
    from fastapi import HTTPException
    mock_client = AsyncMock()
    mock_client.get.return_value = None
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch(
        'src.api.factories.service_factory.ServiceFactory.get_redis_service',
        return_value=mock_rs,
    ):
        from src.api.routers.mcp_router import get_session_recap
        with pytest.raises(HTTPException) as exc:
            await get_session_recap("nonexistent_session")

    assert exc.value.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_cold_start_recap_endpoint.py -v
```

Expected: `ImportError` — `get_session_recap` doesn't exist yet.

- [ ] **Step 3: Add the recap function and route to mcp_router.py**

`json` is already imported at line 5. `get_current_user` is already imported from `src.api.security_auth` at line 49 — use it for API key auth (same pattern as all other routes).

Add near the end of `mcp_router.py`, before the final module-level code:

```python
async def get_session_recap(session_id: str) -> dict:
    """Read last 2 messages from a session's conversation_history in Redis."""
    try:
        rs = await ServiceFactory.get_redis_service()
        raw = await rs._client.get(f"conversation_session:{session_id}")
    except Exception as e:
        logger.warning(f"⚠️ Recap: Redis error for session {session_id}: {e}")
        raise HTTPException(status_code=503, detail="Redis unavailable")

    if not raw:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=500, detail="Session data corrupted")

    history: list = data.get("conversation_history", [])
    last_two = history[-2:] if len(history) >= 2 else history

    return {"session_id": session_id, "turns": last_two}


@router.get("/session/{session_id}/recap")
async def session_recap_endpoint(
    session_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    GET /v1/mcp/session/{session_id}/recap
    Returns the last user+assistant exchange from the session stored in Redis.
    Used by the frontend "Let's continue" cold start flow.
    """
    return await get_session_recap(session_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_cold_start_recap_endpoint.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/api/routers/mcp_router.py tests/unit/test_cold_start_recap_endpoint.py
git commit -m "feat: add GET /v1/mcp/session/{session_id}/recap endpoint"
```

---

## Task 4: Frontend — Add types to widget.ts

**Files:**
- Modify: `src/frontend/src/types/widget.ts`

No tests for type-only changes.

- [ ] **Step 1: Add RecapTurn and ServiceStatus to widget.ts**

In `src/frontend/src/types/widget.ts`, append after the last export:

```typescript
export interface RecapTurn {
  role: 'user' | 'assistant';
  content: string;
}

export type ServiceStatus = 'healthy' | 'warming' | 'down';
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/types/widget.ts
git commit -m "feat: add RecapTurn and ServiceStatus types for cold start UX"
```

---

## Task 5: Frontend — New API methods in api.ts

**Files:**
- Modify: `src/frontend/src/services/api.ts`

- [ ] **Step 1: Add checkHealth() method to ConversationAPI class**

In `src/frontend/src/services/api.ts`, inside the `ConversationAPI` class, add after `updateConfig()`:

```typescript
async checkHealth(): Promise<{ status: string; shutdown_at: number | null }> {
  try {
    const response = await fetch(`${this.config.apiUrl}/health`, {
      method: 'GET',
      headers: { 'X-API-Key': this.config.apiKey },
      signal: AbortSignal.timeout(35_000), // allow cold start up to 35s
    });
    if (!response.ok) return { status: 'unhealthy', shutdown_at: null };
    const data = await response.json();
    return {
      status: data.status ?? 'unknown',
      shutdown_at: data.shutdown_at ?? null,
    };
  } catch {
    return { status: 'unreachable', shutdown_at: null };
  }
}
```

- [ ] **Step 2: Add getSessionRecap() method**

In the same class, add after `checkHealth()`:

```typescript
async getSessionRecap(): Promise<{ turns: import('../types/widget').RecapTurn[] }> {
  try {
    const response = await fetch(
      `${this.config.apiUrl}/v1/mcp/session/${this.sessionId}/recap`,
      {
        method: 'GET',
        headers: { 'X-API-Key': this.config.apiKey },
      },
    );
    if (!response.ok) return { turns: [] };
    const data = await response.json();
    return { turns: Array.isArray(data.turns) ? data.turns : [] };
  } catch {
    return { turns: [] };
  }
}
```

- [ ] **Step 3: Add resetSession() method**

In the same class, add after `getSessionRecap()`:

```typescript
resetSession(): void {
  const newId = `widget_session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  this.sessionId = newId;
  try {
    localStorage.setItem('rr_widget_session_id', newId);
    localStorage.setItem('rr_widget_session_ts', String(Date.now()));
  } catch {
    // localStorage unavailable — session lives in memory
  }
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/services/api.ts
git commit -m "feat: add checkHealth, getSessionRecap, resetSession to ConversationAPI"
```

---

## Task 6: Frontend — ChatWidget new state + Case 1 (health check on open)

**Files:**
- Modify: `src/frontend/src/components/ChatWidget.tsx`

- [ ] **Step 1: Add new state variables**

First, add the import at the **top of ChatWidget.tsx** with the other imports (around line 6):

```typescript
import type { RecapTurn, ServiceStatus } from '../types/widget';
```

Then, after the existing `const [isVisualSearching, setIsVisualSearching] = useState(false);` line (around line 339), add:

```typescript
// Cold start state
const [serviceStatus, setServiceStatus] = useState<ServiceStatus>('healthy');
const [showWarmingOverlay, setShowWarmingOverlay] = useState(false);
const [isResuming, setIsResuming] = useState(false);
const [sessionRecap, setSessionRecap] = useState<RecapTurn[] | null>(null);
const [showInactivityWarning, setShowInactivityWarning] = useState(false);
const lastInteractionRef = useRef<number>(Date.now());
```

- [ ] **Step 2: Add health-check-on-open useEffect (Case 1)**

Add this effect after the existing `useEffect` for resize handling (around line 303):

```typescript
// Case 1: health check on chat open — acts as Cloud Run warm-up trigger
useEffect(() => {
  if (!isOpen) {
    setShowWarmingOverlay(false);
    return;
  }

  let cancelled = false;
  let spinnerTimer: ReturnType<typeof setTimeout>;

  const run = async () => {
    // Only show spinner if health check takes > 1.5s (cold start)
    spinnerTimer = setTimeout(() => {
      if (!cancelled) setShowWarmingOverlay(true);
    }, 1500);

    const health = await api.checkHealth();
    clearTimeout(spinnerTimer);

    if (cancelled) return;
    setShowWarmingOverlay(false);

    if (health.shutdown_at !== null || health.status === 'unreachable') {
      setServiceStatus('down');
    } else {
      setServiceStatus('healthy');
    }
  };

  run();

  return () => {
    cancelled = true;
    clearTimeout(spinnerTimer);
  };
}, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 3: Render warming overlay in ChatWidget JSX**

Find the return JSX of `ChatWidget`. Locate the section that renders the chat panel (the `isOpen` conditional). Inside the chat panel, add the warming overlay as the first child of the message area, conditionally shown:

```tsx
{/* Case 1: Warming overlay while Cloud Run cold-starts */}
{showWarmingOverlay && !hasUserMessages && (
  <div className={styles.warmingOverlay}>
    <div className={styles.spinner} />
    <p className={styles.warmingText}>
      {typeof window !== 'undefined' && localStorage.getItem('rr_widget_session_id')
        ? 'Despertando el asistente… Tu sesión anterior está guardada.'
        : 'Iniciando el asistente…'}
    </p>
  </div>
)}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors (CSS module classes will be added in Task 11).

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/components/ChatWidget.tsx
git commit -m "feat: add Case 1 health-check-on-open cold start detection"
```

---

## Task 7: Frontend — Polling effect + Case 3 + inactivity timer

**Files:**
- Modify: `src/frontend/src/components/ChatWidget.tsx`

- [ ] **Step 1: Add polling useEffect (Cases 2b + 3)**

Add after the health-check effect from Task 6:

```typescript
// Polling: detect shutdown while chat is open (starts after initial health check)
useEffect(() => {
  if (!isOpen || serviceStatus !== 'healthy') return;

  const interval = setInterval(async () => {
    const health = await api.checkHealth();
    if (health.shutdown_at !== null || health.status === 'unreachable') {
      setServiceStatus('down');
    }
  }, 30_000);

  return () => clearInterval(interval);
}, [isOpen, serviceStatus]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 2: Add Case 3 effect (silent close on welcome screen)**

Add immediately after the polling effect:

```typescript
// Case 3: close widget silently when shutdown detected and no conversation
useEffect(() => {
  if (serviceStatus === 'down' && isOpen && !hasUserMessages) {
    setIsOpen(false);
    setServiceStatus('healthy'); // reset so next open triggers Case 1
  }
}, [serviceStatus, isOpen, hasUserMessages]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 3: Add inactivity timer useEffect (Case 2a)**

Add after the Case 3 effect:

```typescript
// Case 2a: 15-min inactivity warning
useEffect(() => {
  if (!isOpen || !hasUserMessages) {
    setShowInactivityWarning(false);
    return;
  }

  const CHECK_INTERVAL_MS = 60_000;       // check every 1 min
  const WARNING_THRESHOLD_MS = 15 * 60_000; // warn at 15 min

  const interval = setInterval(() => {
    const elapsed = Date.now() - lastInteractionRef.current;
    if (elapsed >= WARNING_THRESHOLD_MS) {
      setShowInactivityWarning(true);
    }
  }, CHECK_INTERVAL_MS);

  return () => clearInterval(interval);
}, [isOpen, hasUserMessages]);
```

- [ ] **Step 4: Reset inactivity timer on message send**

Find the `handleSendMessage` (or equivalent) callback in `ChatWidget.tsx`. At the start of the function body add:

```typescript
lastInteractionRef.current = Date.now();
setShowInactivityWarning(false);
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/components/ChatWidget.tsx
git commit -m "feat: add shutdown polling, Case 3 silent close, inactivity timer"
```

---

## Task 8: Frontend — Case 2b service-down card + button handlers

**Files:**
- Modify: `src/frontend/src/components/ChatWidget.tsx`

- [ ] **Step 1: Add button handler functions**

In `ChatWidget.tsx`, add these callbacks after `lastInteractionRef`:

```typescript
const handleLetsContinue = useCallback(async () => {
  setIsResuming(true);
  setServiceStatus('healthy'); // optimistically hide the card

  const recap = await api.getSessionRecap();
  setSessionRecap(recap.turns);

  // Poll /health until service is ready
  const pollUntilReady = async () => {
    const health = await api.checkHealth();
    if (health.shutdown_at === null && health.status !== 'unreachable') {
      setIsResuming(false);
      return;
    }
    setTimeout(pollUntilReady, 5_000);
  };
  pollUntilReady();
}, [api]);

const handleStartNewChat = useCallback(() => {
  api.resetSession();
  setState(prev => ({ ...prev, messages: [] }));
  setServiceStatus('healthy');
  setSessionRecap(null);
  setIsResuming(false);
  setShowInactivityWarning(false);
}, [api]);

const handleCloseConversation = useCallback(() => {
  setIsOpen(false);
  setServiceStatus('healthy');
}, []);
```

- [ ] **Step 2: Render the service-down card in the message area**

In the JSX, inside the messages container (where messages are rendered), add this block — it renders AFTER the existing messages and only when `serviceStatus === 'down' && hasUserMessages`:

```tsx
{serviceStatus === 'down' && hasUserMessages && (
  <div className={styles.serviceDownCard}>
    <div className={styles.serviceDownHeader}>
      <span>💤</span> El asistente ha entrado en reposo
    </div>
    <div className={styles.serviceDownBody}>
      <p className={styles.serviceDownTitle}>Tu conversación está guardada</p>
      <p className={styles.serviceDownSub}>
        Puedes retomar donde lo dejaste o empezar una nueva conversación.
      </p>
      <div className={styles.coldStartActions}>
        <button className={styles.btnPrimary} onClick={handleLetsContinue}>
          Let's continue
        </button>
        <button className={styles.btnSecondary} onClick={handleStartNewChat}>
          Start a new chat
        </button>
        <button className={styles.btnGhost} onClick={handleCloseConversation}>
          Close conversation
        </button>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 3: Add isServiceDown prop to MessageList and apply inactive class**

Bubbles are rendered in `MessageList.tsx`. Add the prop to its interface and apply the class there.

In `src/frontend/src/components/MessageList.tsx`, update the interface (line 244):

```typescript
interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  isServiceDown?: boolean;        // ← add this line
  onChatAbout?: (product: import('../types/widget').ProductRecommendation) => void;
  onShowSimilar?: (product: import('../types/widget').ProductRecommendation) => void;
  onSuggestionClick?: (text: string) => void;
  isExpanded?: boolean;
}
```

Update the function signature (line 261) to destructure the new prop:

```typescript
export function MessageList({ messages, isLoading, isExpanded, isServiceDown, onChatAbout, onShowSimilar, onSuggestionClick }: MessageListProps) {
```

In the message rendering loop inside `MessageList`, find where the user/assistant bubble className is assigned and append the inactive class:

```tsx
// For user bubbles — find the existing className and change it to:
className={`${styles.bubbleUser} ${isServiceDown ? styles.bubbleInactive : ''}`}
// For assistant bubbles:
className={`${styles.bubbleAssistant} ${isServiceDown ? styles.bubbleInactive : ''}`}
```

Back in `ChatWidget.tsx`, pass the prop to `<MessageList>`:

```tsx
<MessageList
  ...existingProps
  isServiceDown={serviceStatus === 'down'}
/>
```

- [ ] **Step 4: Disable input when service is down or resuming**

Find the `MessageInput` component usage in ChatWidget JSX and add the disabled condition:

```tsx
<MessageInput
  ...existingProps
  disabled={state.isLoading || isVisualSearching || serviceStatus === 'down' || isResuming || showWarmingOverlay}
  placeholder={
    serviceStatus === 'down' ? 'Elige una opción arriba…' :
    (showWarmingOverlay || isResuming) ? 'Espera un momento…' :
    undefined  // use the default placeholder
  }
/>
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/components/ChatWidget.tsx
git commit -m "feat: add Case 2b service-down card with Let's continue / Start new chat / Close"
```

---

## Task 9: Frontend — Resuming state render (post "Let's continue")

**Files:**
- Modify: `src/frontend/src/components/ChatWidget.tsx`

- [ ] **Step 1: Render the resuming state in the message area**

In the JSX messages container, add this block after the service-down card (from Task 8). It renders when `isResuming === true`:

```tsx
{isResuming && (
  <div className={styles.resumingContainer}>
    {/* Collapsed recap dropdown */}
    <details className={styles.recapDropdown}>
      <summary className={styles.recapSummary}>
        📋 Ver resumen de conversación anterior
      </summary>
      <div className={styles.recapBody}>
        {(sessionRecap ?? []).map((turn, i) => (
          <div key={i} className={styles.recapRow}>
            <span className={styles.recapRole}>
              {turn.role === 'user' ? 'Tú' : 'AI'}
            </span>
            <span className={styles.recapText}>{turn.content}</span>
          </div>
        ))}
        {(!sessionRecap || sessionRecap.length === 0) && (
          <span className={styles.recapEmpty}>Sin historial disponible</span>
        )}
      </div>
    </details>
    <div className={styles.resumingRow}>
      <div className={styles.spinnerSmall} />
      <span className={styles.resumingText}>Resumiendo conversación…</span>
    </div>
  </div>
)}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/components/ChatWidget.tsx
git commit -m "feat: add resuming state with collapsed recap dropdown"
```

---

## Task 10: Frontend — CSS classes for cold start UI

**Files:**
- Modify: `src/frontend/src/components/ChatWidget.module.css`

- [ ] **Step 1: Add all cold start CSS classes**

Open `src/frontend/src/components/ChatWidget.module.css` and append at the end:

```css
/* ═══════════════════════════════════════════════════════════
   COLD START UX
   ═══════════════════════════════════════════════════════════ */

/* Case 1: Warming overlay */
.warmingOverlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 32px 24px;
  flex: 1;
}

.warmingText {
  font-size: 13px;
  color: #64748b;
  text-align: center;
  line-height: 1.5;
  max-width: 240px;
}

/* Spinner (large — Case 1) */
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #e2e8f0;
  border-top-color: #18181b;
  border-radius: 50%;
  animation: coldStartSpin 0.8s linear infinite;
  flex-shrink: 0;
}

/* Spinner (small — resuming row) */
.spinnerSmall {
  width: 18px;
  height: 18px;
  border: 2px solid #e2e8f0;
  border-top-color: #18181b;
  border-radius: 50%;
  animation: coldStartSpin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes coldStartSpin {
  to { transform: rotate(360deg); }
}

/* Case 2a: Inactivity warning bubble */
.inactivityWarning {
  background: #fefce8;
  border: 1px solid #fde68a;
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 12px;
  color: #78350f;
  line-height: 1.5;
  margin: 4px 0;
}

.inactivityWarning strong {
  display: block;
  font-size: 13px;
  margin-bottom: 4px;
}

/* Case 2b: Inactive bubble styles */
.bubbleInactive {
  opacity: 0.45;
  filter: grayscale(0.3);
}

/* Case 2b: Service-down card */
.serviceDownCard {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  margin: 4px 0;
}

.serviceDownHeader {
  padding: 10px 14px;
  font-size: 12px;
  color: #475569;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.serviceDownBody {
  padding: 12px 14px;
}

.serviceDownTitle {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 6px;
}

.serviceDownSub {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  margin-bottom: 14px;
}

/* Cold start action buttons */
.coldStartActions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.btnPrimary {
  background: #18181b;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 9px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  width: 100%;
  text-align: center;
}

.btnPrimary:hover { background: #27272a; }

.btnSecondary {
  background: white;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
  width: 100%;
  text-align: center;
}

.btnSecondary:hover { background: #f9fafb; }

.btnGhost {
  background: transparent;
  color: #94a3b8;
  border: none;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 12px;
  cursor: pointer;
  width: 100%;
  text-align: center;
}

.btnGhost:hover { color: #64748b; }

/* Post "Let's continue": resuming container */
.resumingContainer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 4px 0;
}

.resumingRow {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 2px;
}

.resumingText {
  font-size: 12px;
  color: #64748b;
}

/* Recap dropdown (uses native <details>) */
.recapDropdown {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  font-size: 12px;
}

.recapSummary {
  padding: 8px 12px;
  background: #f8fafc;
  cursor: pointer;
  color: #64748b;
  list-style: none;
  user-select: none;
}

.recapSummary::-webkit-details-marker { display: none; }
.recapSummary::marker { display: none; }

.recapBody {
  padding: 10px 12px;
  background: white;
  border-top: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.recapRow {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.recapRole {
  font-weight: 600;
  color: #475569;
  min-width: 24px;
  font-size: 11px;
  padding-top: 1px;
  flex-shrink: 0;
}

.recapText {
  color: #374151;
  line-height: 1.4;
}

.recapEmpty {
  color: #94a3b8;
  font-style: italic;
}
```

- [ ] **Step 2: Verify no CSS syntax errors by checking TypeScript compile**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/components/ChatWidget.module.css
git commit -m "feat: add CSS classes for cold start UI states"
```

---

## Task 11: Build widget + smoke test

**Files:**
- `static/widget/widget.umd.cjs` (regenerated by build)

- [ ] **Step 1: Run the full test suite**

```bash
pytest -m "not slow and not debug and not e2e" -v
```

Expected: all tests pass including the 9 new cold start tests.

- [ ] **Step 2: Build the frontend widget**

```bash
cd src/frontend && npm run build
```

Expected: build completes with no TypeScript errors. `dist/widget.umd.cjs` is generated.

- [ ] **Step 3: Copy build output to static/**

```bash
cp src/frontend/dist/widget.umd.cjs static/widget/widget.umd.cjs
cp src/frontend/dist/widget.umd.cjs.map static/widget/widget.umd.cjs.map
```

- [ ] **Step 4: Manual smoke test — Case 1 (warm service)**

Start the API locally:
```bash
uvicorn src.api.main_unified_redis:app --reload --port 8000
```

Open a browser to `http://localhost:8000`. Click the chat bubble. Expected: chat opens immediately with no spinner (service is warm → health check responds in < 1.5s).

- [ ] **Step 5: Manual smoke test — Case 1 (simulated cold start)**

Without the server running, open the widget page. Click the chat bubble. Expected: spinner appears after 1.5s with warm-up text. Once server starts, spinner disappears.

- [ ] **Step 6: Manual smoke test — Case 2b (shutdown card)**

Send a message in the chat. Then in the browser console run:
```javascript
// Simulate shutdown detection (sets the React state directly via hook — use browser devtools React inspector)
```

Or: stop the server, wait 30s for the next poll cycle. Expected: bubbles fade, service-down card appears with 3 buttons.

- [ ] **Step 7: Commit**

```bash
git add static/widget/widget.umd.cjs static/widget/widget.umd.cjs.map
git commit -m "feat: build widget with cold start UX"
```
