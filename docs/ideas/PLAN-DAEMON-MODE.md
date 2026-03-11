# Plan: Daemon Mode for Workspace Supervisor

> Priority: HIGH | Effort: MODERATE
> Inspired by: Symphony's continuous polling orchestrator

## Goal

Replace the manual `/workspace run` trigger with a persistent background daemon that automatically watches `registry.json` for new tasks and dispatches agents. The system becomes truly autonomous — add a task via dashboard or CLI, and it gets picked up within seconds.

---

## Architecture Overview

```
                    ┌─────────────────────────────────┐
                    │     Supervisor Daemon            │
                    │     (dashboard/daemon.py)        │
                    │                                  │
                    │  ┌───────────────────────────┐   │
                    │  │  Poll Loop (configurable)  │   │
                    │  │  - Watch registry.json     │   │
 registry.json ────│──│  - Watch github issues      │   │
 (file changes)    │  │  - Check retry queue        │   │
                    │  └───────────┬───────────────┘   │
                    │              │                    │
                    │              ▼                    │
                    │  ┌───────────────────────────┐   │
                    │  │  Dispatcher                │   │
                    │  │  - Concurrency control     │   │
                    │  │  - Priority sorting        │   │
                    │  │  - Agent spawning          │   │
                    │  └───────────┬───────────────┘   │
                    │              │                    │
                    │              ▼                    │
                    │  ┌───────────────────────────┐   │
                    │  │  Run Manager               │   │
                    │  │  - Track active runs       │   │
                    │  │  - Retry with backoff      │   │
                    │  │  - Timeout handling        │   │
                    │  └───────────────────────────┘   │
                    └─────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              workspace-     /fix-the-issue   /scrum-team
              supervisor        agent           agent
```

## Implementation Steps

### Step 1: Daemon Core

**File**: `dashboard/daemon.py` — new module (~250 lines)

```python
class SupervisorDaemon:
    """Persistent daemon that watches registry for pending tasks."""

    def __init__(self, config):
        self.config = config
        self.active_runs = {}          # run_id → RunInfo
        self.retry_queue = []          # [(due_time, task_info)]
        self.processed_tasks = set()   # Prevent double-dispatch
        self.running = True

    def start(self):
        """Main loop — poll, dispatch, reconcile."""
        while self.running:
            self._poll_tick()
            self._check_retries()
            self._reconcile_active_runs()
            time.sleep(self.config.poll_interval_s)

    def _poll_tick(self):
        """Single poll cycle."""
        registry = read_registry()
        pending = self._find_pending_tasks(registry)
        pending = self._sort_by_priority(pending)
        pending = self._filter_by_concurrency(pending)

        for task_info in pending:
            self._dispatch(task_info)

    def _dispatch(self, task_info):
        """Spawn agent for a task."""
        # 1. Update registry: status → in_progress
        # 2. Choose agent based on task type/title
        # 3. Spawn subprocess
        # 4. Track in active_runs
        pass

    def _reconcile_active_runs(self):
        """Check active runs for completion/failure."""
        for run_id, info in list(self.active_runs.items()):
            if info.process.poll() is not None:
                exit_code = info.process.returncode
                if exit_code == 0:
                    self._mark_done(info)
                else:
                    self._handle_failure(info)
                del self.active_runs[run_id]

    def _handle_failure(self, info):
        """Schedule retry with exponential backoff."""
        attempt = info.attempt + 1
        if attempt > self.config.max_retries:
            self._mark_blocked(info, "Max retries exceeded")
            return
        delay = min(
            self.config.base_backoff_s * (2 ** attempt),
            self.config.max_backoff_s
        )
        due_time = time.time() + delay
        self.retry_queue.append((due_time, info.with_attempt(attempt)))
```

### Step 2: Configuration

**File**: `~/.claude/workspace/daemon-config.json`

```json
{
  "enabled": true,
  "poll_interval_s": 10,
  "max_concurrent_agents": 3,
  "max_retries": 3,
  "base_backoff_s": 30,
  "max_backoff_s": 300,
  "task_timeout_s": 3600,
  "dispatch_rules": [
    {
      "match": { "type": "coding", "title_contains": ["fix", "bug"] },
      "workflow": "fix-the-issue"
    },
    {
      "match": { "type": "coding", "title_contains": ["feature", "add", "implement"] },
      "workflow": "scrum-team --auto --size small"
    },
    {
      "match": { "type": "brainstorm" },
      "workflow": "brainstorm"
    },
    {
      "match": {},
      "workflow": "supervisor"
    }
  ]
}
```

### Step 3: Integration with Dashboard Server

**File**: `dashboard/server.py` — modifications

The daemon runs as a thread inside the existing dashboard server process (no separate process to manage):

```python
# In main():
daemon_config = load_daemon_config()
if daemon_config.get("enabled"):
    daemon = SupervisorDaemon(daemon_config)
    daemon_thread = threading.Thread(target=daemon.start, daemon=True)
    daemon_thread.start()
    print(f"  Daemon: enabled (poll every {daemon_config['poll_interval_s']}s)")
```

New API endpoints:
```
GET  /api/daemon/status      — Running state, active runs, retry queue
POST /api/daemon/start       — Enable daemon
POST /api/daemon/stop        — Disable daemon (graceful)
POST /api/daemon/config      — Update config (hot-reload)
GET  /api/daemon/runs        — Active + recent completed runs
```

### Step 4: File System Watcher (Optimization)

Instead of polling `registry.json` on a fixed interval, use `fswatch` or `inotify` to react instantly to file changes:

```python
import select  # kqueue on macOS

class RegistryWatcher:
    """Watch registry.json for modifications using kqueue (macOS)."""

    def __init__(self, path, callback):
        self.path = path
        self.callback = callback
        self.last_mtime = 0

    def watch(self):
        """Fallback: poll mtime every 2s (works on all platforms)."""
        while True:
            try:
                mtime = os.path.getmtime(self.path)
                if mtime > self.last_mtime:
                    self.last_mtime = mtime
                    self.callback()
            except FileNotFoundError:
                pass
            time.sleep(2)
```

### Step 5: launchd Service (macOS)

**File**: `dashboard/install-daemon.sh` — installer script

Creates `~/Library/LaunchAgents/ai.dodocs.workspace-daemon.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.dodocs.workspace-daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>~/.claude/dashboard/server.py</string>
        <string>--daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>~/.claude/workspace/daemon.log</string>
    <key>StandardErrorPath</key>
    <string>~/.claude/workspace/daemon.err</string>
</dict>
</plist>
```

### Step 6: Dashboard UI

**File**: `dashboard/ui/src/components/DaemonPanel.jsx` — new component

- Status indicator: green dot (running) / red dot (stopped)
- Active runs list with progress indicators
- Retry queue display
- Config toggle (enable/disable, concurrency limit slider)
- Log viewer (tail daemon output)

### Step 7: CLI Integration

Update `/workspace` skill:
```
/workspace daemon start   — Start daemon mode
/workspace daemon stop    — Stop daemon mode
/workspace daemon status  — Show daemon state
/workspace daemon config  — Show/edit daemon config
```

---

## State Machine for Runs

```
               ┌──────────┐
               │  PENDING  │ ← task created in registry
               └─────┬─────┘
                     │ daemon picks up
                     ▼
               ┌──────────┐
               │DISPATCHED│ ← agent subprocess spawned
               └─────┬─────┘
                     │ process starts
                     ▼
               ┌──────────┐
               │  RUNNING  │ ← agent executing
               └─────┬─────┘
                     │
              ┌──────┼──────┐
              ▼             ▼
        ┌──────────┐  ┌──────────┐
        │ SUCCESS  │  │  FAILED  │
        └──────────┘  └─────┬────┘
                           │ retry eligible?
                    ┌──────┼──────┐
                    ▼             ▼
              ┌──────────┐  ┌──────────┐
              │  RETRY   │  │ BLOCKED  │ ← max retries exceeded
              │ SCHEDULED│  └──────────┘
              └─────┬────┘
                    │ backoff expires
                    ▼
              ┌──────────┐
              │DISPATCHED│ ← re-dispatch
              └──────────┘
```

---

## Concurrency Control

```python
def _filter_by_concurrency(self, pending):
    """Respect concurrency limits."""
    available_slots = self.config.max_concurrent_agents - len(self.active_runs)
    if available_slots <= 0:
        return []
    return pending[:available_slots]
```

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Runaway agent consuming resources | Task timeout (default 1h), kill subprocess |
| Registry corruption from concurrent writes | File locking with `fcntl.flock()` |
| Daemon crashes | launchd `KeepAlive` auto-restarts |
| Too many concurrent agents | Configurable `max_concurrent_agents` (default 3) |
| Stale tasks stuck in `in_progress` | Reconciliation on startup: check PIDs, reset orphans to `pending` |

## Estimated Scope

- `daemon.py`: ~350 lines (core daemon + dispatcher + retry)
- `server.py` changes: ~80 lines (daemon thread + API endpoints)
- `install-daemon.sh`: ~40 lines
- Dashboard UI: ~150 lines (DaemonPanel)
- CLI changes: ~30 lines
- **Total: ~650 lines new code**
