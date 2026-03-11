# Plan: SSE Event Stream for Real-Time Dashboard

> Priority: HIGH | Effort: LOW-MODERATE
> Inspired by: Symphony's `/api/v1/status` and event streaming

## Goal

Replace the dashboard's 10-second polling with Server-Sent Events (SSE) for instant real-time updates. The backend infrastructure already exists (`EventStore` with subscribers and `/api/events/stream`). This plan focuses on wiring the frontend to use it and enriching the event types.

---

## Current State

### What Already Works (Backend)

`dashboard/server.py` already has:
- `EventStore` singleton with thread-safe subscriber pattern (line 85-399)
- `subscribe()` / `unsubscribe()` methods using `queue.Queue` (line 388-399)
- SSE endpoint `GET /api/events/stream` with keepalive (line 916-939)
- File watcher that tails daily `events-*.jsonl` and fans out to subscribers (line 247-293)
- Webhook ingestion `POST /api/webhook/event` (line 965-972)

### What's Missing (Frontend)

`dashboard/ui/src/App.jsx` currently polls `/api/registry` every 10 seconds:
```javascript
// Current: polling loop
useEffect(() => {
  const interval = setInterval(() => fetchRegistry(), 10000);
  return () => clearInterval(interval);
}, []);
```

No SSE consumption exists in the frontend.

---

## Implementation Steps

### Step 1: Enrich Backend Events

**File**: `dashboard/server.py`

Currently events come only from hooks (external tool calls). Add server-side event emission for registry changes:

```python
# In write_registry():
def write_registry(data: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    # Emit SSE event for registry change
    store = EventStore()
    store._ingest({
        "event": "registry_updated",
        "ts": now_iso(),
        "session_id": "dashboard-server",
        "source": "server",
    })
```

Add events for key operations:
| Event | Trigger | Payload |
|-------|---------|---------|
| `registry_updated` | Any registry write | `{}` (client re-fetches full registry) |
| `task_created` | POST /api/projects/{id}/tasks | `{ project_id, task_id, title }` |
| `task_updated` | Task status change | `{ project_id, task_id, status, result }` |
| `supervisor_started` | POST /api/supervisor/run | `{ run_id, pid, task_ids }` |
| `supervisor_completed` | Supervisor process exits | `{ run_id, exit_code }` |
| `daemon_status` | Daemon state change | `{ running, active_runs, queue_depth }` |

### Step 2: Frontend SSE Hook

**File**: `dashboard/ui/src/hooks/useEventStream.js` — new file

```javascript
import { useEffect, useRef, useCallback } from 'react';

export function useEventStream(onEvent) {
  const esRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (esRef.current) return;

    const es = new EventSource('/api/events/stream');
    esRef.current = es;

    es.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data);
        onEvent(event);
      } catch (e) {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      es.close();
      esRef.current = null;
      // Reconnect with backoff
      reconnectTimer.current = setTimeout(connect, 3000);
    };
  }, [onEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (esRef.current) esRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connect]);
}
```

### Step 3: Wire App.jsx to SSE

**File**: `dashboard/ui/src/App.jsx` — modify

Replace polling with SSE + on-demand refresh:

```javascript
import { useEventStream } from './hooks/useEventStream';

function App() {
  const [registry, setRegistry] = useState(null);

  const fetchRegistry = useCallback(async () => {
    const res = await fetch('/api/registry');
    const data = await res.json();
    setRegistry(data);
  }, []);

  // Initial load
  useEffect(() => { fetchRegistry(); }, []);

  // SSE: refresh on registry changes
  const handleEvent = useCallback((event) => {
    if (event.event === 'registry_updated' ||
        event.event === 'task_created' ||
        event.event === 'task_updated') {
      fetchRegistry();  // Re-fetch full registry
    }
    // Could also handle granular updates for specific components
  }, [fetchRegistry]);

  useEventStream(handleEvent);

  // Remove the 10s polling interval
  // ...
}
```

### Step 4: Live Activity Feed Component

**File**: `dashboard/ui/src/components/LiveFeed.jsx` — new component

A real-time event ticker shown in the sidebar or as a collapsible panel:

```javascript
function LiveFeed() {
  const [events, setEvents] = useState([]);

  const handleEvent = useCallback((event) => {
    setEvents(prev => [...prev.slice(-49), event]); // Keep last 50
  }, []);

  useEventStream(handleEvent);

  return (
    <div className="live-feed">
      <h3>Live Activity</h3>
      {events.map((evt, i) => (
        <div key={i} className={`feed-item ${evt.event}`}>
          <span className="time">{formatTime(evt.ts)}</span>
          <span className="event">{formatEvent(evt)}</span>
        </div>
      ))}
    </div>
  );
}
```

### Step 5: Session Activity Tab — SSE Upgrade

**File**: `dashboard/ui/src/components/SessionTab.jsx` — modify

Currently auto-refreshes every 5s. Replace with SSE filtered by project:

```javascript
// Replace polling with SSE
useEventStream(useCallback((event) => {
  if (event.cwd && event.cwd.startsWith(project.path)) {
    setSessionEvents(prev => [...prev, event]);
  }
}, [project.path]));
```

### Step 6: Connection Status Indicator

**File**: `dashboard/ui/src/components/ConnectionStatus.jsx` — new component

Small indicator showing SSE connection health:
- Green dot: connected, receiving events
- Yellow dot: reconnecting
- Red dot: disconnected

```javascript
function ConnectionStatus() {
  const [status, setStatus] = useState('connecting');

  // Track EventSource state
  // Show in top-right corner of dashboard
}
```

---

## Fallback Strategy

Keep a slow polling fallback (every 60s) in case SSE connection drops for extended periods. This ensures the dashboard never shows stale data even if the browser tab was backgrounded (browsers throttle SSE in background tabs).

```javascript
// Slow fallback poll (safety net)
useEffect(() => {
  const fallback = setInterval(fetchRegistry, 60000);
  return () => clearInterval(fallback);
}, []);
```

---

## Event Types Reference

### Agent Lifecycle Events (from hooks)
These already exist, emitted by Claude Code hooks:
- `SessionStart` — agent session begins
- `SessionEnd` — agent session ends
- `ToolUse` — agent calls a tool
- `Message` — agent produces output

### Dashboard Events (new)
Emitted by the server itself:
- `registry_updated` — any registry write
- `task_created` — new task added
- `task_updated` — task status/result changed
- `supervisor_started` — supervisor run dispatched
- `supervisor_completed` — supervisor run finished
- `daemon_status` — daemon state change (if daemon mode enabled)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Browser throttles SSE in background tabs | 60s fallback polling |
| Too many events → UI flicker | Debounce registry re-fetches (300ms) |
| SSE connection drops | Auto-reconnect with 3s backoff |
| Memory leak from event accumulation | Cap in-memory events at 50 in LiveFeed |

## Estimated Scope

- `server.py` changes: ~30 lines (emit events on registry writes)
- `useEventStream.js`: ~40 lines (new hook)
- `App.jsx` changes: ~20 lines (replace polling with SSE)
- `LiveFeed.jsx`: ~60 lines (new component)
- `ConnectionStatus.jsx`: ~30 lines (new component)
- `SessionTab.jsx` changes: ~15 lines (SSE upgrade)
- **Total: ~195 lines changed/new code**

This is the lowest-effort, highest-immediate-impact of the three plans since most of the backend infrastructure already exists.
