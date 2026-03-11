#!/usr/bin/env python3
"""
AI Workspace OS Dashboard Server
Serves the dashboard SPA and provides REST API for registry operations.
Port: 7474, stdlib only — no pip required.
"""

import collections
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from uuid import uuid4

REGISTRY_PATH = Path.home() / ".claude" / "workspace" / "registry.json"
PROJECTS_DIR = Path.home() / ".claude" / "workspace" / "projects"
RUNS_DIR = Path.home() / ".claude" / "workspace" / "runs"
EVENTS_DIR = Path.home() / ".claude" / "workspace" / "events"
SESSIONS_DIR = Path.home() / ".claude" / "workspace" / "sessions"
SESSIONS_INDEX = SESSIONS_DIR / "sessions.jsonl"
DASHBOARD_DIR = Path(__file__).parent
PORT = 7474
MAX_EVENTS_PER_SESSION = 500
MAX_TOTAL_EVENTS = 5000
STALE_THRESHOLD_SECONDS = 300  # 5 min = inactive

EXCLUDE_DIRS = {
    '.git', 'node_modules', '__pycache__', 'target', '.venv', 'venv',
    '.idea', 'dist', 'build', '.next', 'coverage', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.tox', 'htmlcov',
}


# ── Worktree / project resolution ────────────────────────────────────────

def resolve_project(cwd):
    """Detect if cwd is inside a worktree and resolve to the main project."""
    path = cwd or ""
    is_worktree = False
    worktree_name = None
    main_project_path = path

    # Pattern 1: /.claude/worktrees/<name> in the path
    if '/.claude/worktrees/' in path:
        parts = path.split('/.claude/worktrees/')
        main_project_path = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        worktree_name = rest.split('/')[0] if rest else None
        is_worktree = True
    else:
        # Pattern 2: .git file (git worktree indicator) pointing to main repo
        git_path = Path(path) / '.git' if path else None
        if git_path and git_path.exists() and git_path.is_file():
            try:
                content = git_path.read_text().strip()
                if content.startswith('gitdir:'):
                    gitdir = content[7:].strip()
                    if '/worktrees/' in gitdir:
                        main_git = gitdir.split('/worktrees/')[0]
                        main_project_path = str(Path(main_git).parent)
                        worktree_name = gitdir.split('/worktrees/')[-1].rstrip('/')
                        is_worktree = True
            except Exception:
                pass

    project_name = main_project_path.rstrip('/').split('/')[-1] if main_project_path else ''

    return {
        'project_path': main_project_path,
        'project_name': project_name,
        'is_worktree': is_worktree,
        'worktree_name': worktree_name,
        'cwd': cwd,
    }


# ── EventStore (thread-safe singleton) ─────────────────────────────────────

class EventStore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self.sessions = collections.defaultdict(lambda: collections.deque(maxlen=MAX_EVENTS_PER_SESSION))
        self.all_events = collections.deque(maxlen=MAX_TOTAL_EVENTS)
        self.session_meta = {}
        self.subscribers = []
        self._sub_lock = threading.Lock()
        self._file_positions = {}
        self._load_session_index()
        self._load_recent_events()
        self._compact_session_index()
        self._start_file_watcher()

    # ── Session index persistence ─────────────────────────────────────────

    def _load_session_index(self):
        """Load session metadata from sessions.jsonl, keeping last entry per session_id."""
        if not SESSIONS_INDEX.exists():
            self._backfill_session_index()
            return
        try:
            with open(SESSIONS_INDEX) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            meta = json.loads(line)
                            sid = meta.get("session_id")
                            if sid:
                                self.session_meta[sid] = meta
                        except json.JSONDecodeError:
                            pass
            print(f"  Loaded {len(self.session_meta)} sessions from index")
        except Exception as e:
            print(f"  Warning: failed to load session index: {e}")

    def _backfill_session_index(self):
        """Build session index from all historical event files (first run)."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        if not EVENTS_DIR.exists():
            return
        count = 0
        for event_file in sorted(EVENTS_DIR.glob("events-*.jsonl")):
            try:
                with open(event_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                evt = json.loads(line)
                                self._update_session_meta(evt)
                                count += 1
                            except json.JSONDecodeError:
                                pass
            except Exception:
                pass
        self._compact_session_index()
        print(f"  Backfilled session index from {count} events")

    def _update_session_meta(self, event):
        """Update in-memory session metadata from an event."""
        sid = event.get("session_id")
        if not sid or sid == "unknown":
            return

        ts = event.get("ts", "")
        evt_type = event.get("event", "")
        cwd = event.get("cwd", "")

        if sid not in self.session_meta:
            proj = resolve_project(cwd)
            self.session_meta[sid] = {
                "session_id": sid,
                "project_path": proj["project_path"],
                "project_name": proj["project_name"],
                "cwd": cwd,
                "is_worktree": proj["is_worktree"],
                "worktree_name": proj["worktree_name"],
                "started_at": ts,
                "last_activity": ts,
                "event_count": 0,
                "last_event": evt_type,
                "status": "active",
            }

        meta = self.session_meta[sid]
        if ts:
            meta["last_activity"] = ts
        meta["event_count"] = meta.get("event_count", 0) + 1
        meta["last_event"] = evt_type

        # Fill in cwd/project if we didn't have it
        if cwd and not meta.get("cwd"):
            proj = resolve_project(cwd)
            meta["cwd"] = cwd
            meta["project_path"] = proj["project_path"]
            meta["project_name"] = proj["project_name"]
            meta["is_worktree"] = proj["is_worktree"]
            meta["worktree_name"] = proj["worktree_name"]

        if evt_type == "SessionEnd":
            meta["status"] = "ended"

    def _compact_session_index(self):
        """Rewrite session index with one line per session (deduped)."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(SESSIONS_INDEX, "w") as f:
                for meta in self.session_meta.values():
                    f.write(json.dumps(meta) + "\n")
        except Exception:
            pass

    def _append_session_index(self, sid):
        """Append a single session update to the index file."""
        meta = self.session_meta.get(sid)
        if not meta:
            return
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(SESSIONS_INDEX, "a") as f:
                f.write(json.dumps(meta) + "\n")
        except Exception:
            pass

    # ── File watcher (reads events written by hooks) ──────────────────────

    def _load_recent_events(self):
        """Load today's events from file into memory."""
        today = datetime.now().strftime("%Y-%m-%d")
        path = EVENTS_DIR / f"events-{today}.jsonl"
        if not path.exists():
            self._file_positions[today] = 0
            return
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            evt = json.loads(line)
                            sid = evt.get("session_id", "unknown")
                            self.sessions[sid].append(evt)
                            self.all_events.append(evt)
                            self._update_session_meta(evt)
                        except json.JSONDecodeError:
                            pass
                self._file_positions[today] = f.tell()
            print(f"  Loaded {len(self.all_events)} events from {path.name}")
        except Exception as e:
            print(f"  Warning: failed to load events: {e}")

    def _start_file_watcher(self):
        """Start background thread that tails daily event files."""
        t = threading.Thread(target=self._watch_loop, daemon=True)
        t.start()

    def _watch_loop(self):
        while True:
            time.sleep(1)
            today = datetime.now().strftime("%Y-%m-%d")
            path = EVENTS_DIR / f"events-{today}.jsonl"
            if not path.exists():
                continue
            pos = self._file_positions.get(today, 0)
            try:
                size = path.stat().st_size
                if size <= pos:
                    continue
                with open(path) as f:
                    f.seek(pos)
                    new_data = f.read()
                    self._file_positions[today] = f.tell()
                for line in new_data.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            evt = json.loads(line)
                            self._ingest(evt)
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass

    def _ingest(self, event):
        """Add event to in-memory stores and fan out to SSE. Does NOT write to file."""
        sid = event.get("session_id", "unknown")
        self.sessions[sid].append(event)
        self.all_events.append(event)
        self._update_session_meta(event)
        self._append_session_index(sid)
        # Fan-out to SSE subscribers
        data = json.dumps(event)
        with self._sub_lock:
            for q in self.subscribers:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass

    def add(self, event):
        """Write event to daily JSONL file. The file watcher will pick it up."""
        event.setdefault("ts", now_iso())
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        path = EVENTS_DIR / f"events-{today}.jsonl"
        try:
            with open(path, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass

    # ── Query methods ─────────────────────────────────────────────────────

    def get_all(self, limit=200, since=None):
        events = list(self.all_events)
        if since:
            events = [e for e in events if e.get("ts", "") > since]
        return events[-limit:]

    def get_session(self, session_id, limit=200):
        return list(self.sessions.get(session_id, []))[-limit:]

    def get_sessions_summary(self, project_path=None):
        now = datetime.now(timezone.utc)
        result = []
        for sid, meta in self.session_meta.items():
            if project_path and meta.get("project_path") != project_path:
                continue
            entry = dict(meta)
            # Compute effective status at read time
            if entry.get("status") != "ended":
                last = entry.get("last_activity", "")
                try:
                    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    age = (now - last_dt).total_seconds()
                    entry["status"] = "active" if age < STALE_THRESHOLD_SECONDS else "inactive"
                except Exception:
                    entry["status"] = "inactive"
            result.append(entry)
        result.sort(key=lambda x: x.get("last_activity", ""), reverse=True)
        return result

    def get_session_history(self, session_id, limit=500):
        """Get full event history for a session from all daily files on disk."""
        events = []
        if not EVENTS_DIR.exists():
            return events
        for event_file in sorted(EVENTS_DIR.glob("events-*.jsonl")):
            try:
                with open(event_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                evt = json.loads(line)
                                if evt.get("session_id") == session_id:
                                    events.append(evt)
                            except json.JSONDecodeError:
                                pass
            except Exception:
                pass
        return events[-limit:]

    def get_events_for_date(self, date_str, limit=500):
        """Load events from a specific date's file."""
        path = EVENTS_DIR / f"events-{date_str}.jsonl"
        if not path.exists():
            return []
        events = []
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
        return events[-limit:]

    def get_event_dates(self):
        """List dates that have event files, newest first."""
        if not EVENTS_DIR.exists():
            return []
        dates = []
        for f in sorted(EVENTS_DIR.glob("events-*.jsonl"), reverse=True):
            date_str = f.stem.replace("events-", "")
            dates.append(date_str)
        return dates

    def subscribe(self):
        q = queue.Queue(maxsize=256)
        with self._sub_lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._sub_lock:
            try:
                self.subscribers.remove(q)
            except ValueError:
                pass


# ── Registry helpers ───────────────────────────────────────────────────────

def read_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"version": "1.0", "workspaces": ["personal", "corporate"], "projects": []}
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def write_registry(data: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def get_project(registry: dict, project_id: str):
    return next((p for p in registry.get("projects", []) if p["id"] == project_id), None)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def next_project_id(projects: list) -> str:
    nums = []
    for p in projects:
        pid = p.get("id", "")
        if pid.startswith("proj-"):
            try:
                nums.append(int(pid[5:]))
            except ValueError:
                pass
    return f"proj-{(max(nums, default=0) + 1):03d}"


def next_task_id(projects: list) -> str:
    nums = []
    for p in projects:
        for t in p.get("tasks", []):
            tid = t.get("id", "")
            if tid.startswith("task-"):
                try:
                    nums.append(int(tid[5:]))
                except ValueError:
                    pass
    return f"task-{(max(nums, default=0) + 1):03d}"


# ── Log helper ─────────────────────────────────────────────────────────────

def read_log(project_id: str, lines: int = 100) -> list:
    log_path = PROJECTS_DIR / project_id / "log.jsonl"
    if not log_path.exists():
        return []
    with open(log_path) as f:
        all_lines = f.readlines()
    result = []
    for line in all_lines[-lines:]:
        line = line.strip()
        if line:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return result


# ── Project detail helpers ─────────────────────────────────────────────────

def scan_docs(project: dict) -> list:
    """Scan project path for documentation files up to 2 levels deep."""
    path = project.get("path", "")
    if not path or not Path(path).exists():
        return []
    root = Path(path)
    results = []
    seen = set()

    def add(f: Path):
        try:
            rel = str(f.relative_to(root))
            if rel not in seen and f.is_file():
                seen.add(rel)
                stat = f.stat()
                results.append({
                    "name": f.name,
                    "rel_path": rel,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
        except Exception:
            pass

    # Root-level docs
    for ext in ("*.md", "*.txt", "*.rst"):
        for f in sorted(root.glob(ext)):
            add(f)

    # docs/ directory (recursive)
    docs_dir = root / "docs"
    if docs_dir.exists():
        for ext in ("*.md", "*.txt", "*.rst"):
            for f in sorted(docs_dir.rglob(ext)):
                add(f)

    # One level deep subdirectories
    try:
        for subdir in sorted(root.iterdir()):
            if subdir.is_dir() and subdir.name not in EXCLUDE_DIRS and not subdir.name.startswith(".") and subdir.name != "docs":
                for ext in ("*.md", "*.txt"):
                    for f in sorted(subdir.glob(ext)):
                        add(f)
    except PermissionError:
        pass

    results.sort(key=lambda x: (x["rel_path"].count("/"), x["name"].lower()))
    return results[:100]


def read_doc_file(project: dict, rel_path: str) -> dict:
    """Read a file from within the project directory. Security: path must stay inside project root."""
    path = project.get("path", "")
    if not path or not rel_path:
        return {"error": "Not found"}
    try:
        root = Path(path).resolve()
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root)):
            return {"error": "Access denied"}
        if not target.exists() or not target.is_file():
            return {"error": "File not found"}
        size = target.stat().st_size
        raw = target.read_text(errors="replace")
        if target.suffix == ".jsonl":
            lines = raw.splitlines()
            total = len(lines)
            shown = lines[-80:]
            note = f"[Showing last {len(shown)} of {total} lines — {size // 1024}KB file]\n\n" if total > len(shown) else ""
            raw = note + "\n".join(shown)
        elif size > 400_000:
            raw = raw[:400_000] + "\n\n[... file truncated at 400KB ...]"
        return {"content": raw, "name": target.name, "rel_path": rel_path, "size": size}
    except Exception as e:
        return {"error": str(e)}


def build_tree(project: dict) -> list:
    """Build directory tree (depth 2), excluding noise dirs."""
    path = project.get("path", "")
    if not path or not Path(path).exists():
        return []

    def scan(p: Path, depth: int) -> list:
        entries = []
        try:
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return []
        for item in items:
            if item.name.startswith("."):
                continue
            if item.is_dir() and item.name in EXCLUDE_DIRS:
                continue
            entry = {"name": item.name, "type": "dir" if item.is_dir() else "file"}
            if item.is_dir():
                if depth < 2:
                    entry["children"] = scan(item, depth + 1)
                else:
                    try:
                        entry["child_count"] = sum(1 for _ in item.iterdir() if not _.name.startswith("."))
                    except Exception:
                        entry["child_count"] = 0
            entries.append(entry)
        return entries

    return scan(Path(path), 1)


def scan_sessions(project: dict, project_id: str) -> dict:
    """Return workspace activity log + Claude session files found in project."""
    log = read_log(project_id)
    sessions = []
    path = project.get("path", "")
    if path and Path(path).exists():
        root = Path(path)
        # Session continuation .txt files (Claude "continuing from previous session")
        try:
            for f in sorted(root.glob("*.txt"), key=lambda x: -x.stat().st_mtime):
                sessions.append({
                    "name": f.name, "rel_path": str(f.relative_to(root)),
                    "size": f.stat().st_size, "modified": f.stat().st_mtime, "type": "session-txt",
                })
        except Exception:
            pass
        # tasks/ markdown files
        tasks_dir = root / "tasks"
        if tasks_dir.exists():
            try:
                for f in sorted(tasks_dir.glob("*.md"), key=lambda x: -x.stat().st_mtime):
                    sessions.append({
                        "name": f"tasks/{f.name}", "rel_path": str(f.relative_to(root)),
                        "size": f.stat().st_size, "modified": f.stat().st_mtime, "type": "task-md",
                    })
            except Exception:
                pass
        # .jsonl transcript files
        try:
            for f in sorted(root.glob("*.jsonl"), key=lambda x: -x.stat().st_mtime):
                sessions.append({
                    "name": f.name, "rel_path": str(f.relative_to(root)),
                    "size": f.stat().st_size, "modified": f.stat().st_mtime, "type": "jsonl",
                })
        except Exception:
            pass
    return {"log": log, "sessions": sessions[:30]}


def read_context_md(project_id: str) -> str:
    """Read the workspace context.md for a project."""
    path = PROJECTS_DIR / project_id / "context.md"
    if path.exists():
        return path.read_text(errors="replace")
    return ""


# ── Supervisor helper ──────────────────────────────────────────────────────

def _spawn_supervisor():
    """Spawn the workspace-supervisor agent in background. Returns (proc, run_id)."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    log_path = RUNS_DIR / f"{run_id}.log"

    # Collect pending task IDs and project IDs
    registry = read_registry()
    pending_task_ids = []
    pending_project_ids = set()
    for proj in registry.get("projects", []):
        for task in proj.get("tasks", []):
            if task.get("status") == "pending":
                pending_task_ids.append(task["id"])
                pending_project_ids.add(proj["id"])
                task["run_id"] = run_id
    write_registry(registry)

    # Write sidecar meta file
    meta = {
        "run_id": run_id,
        "started_at": now_iso(),
        "task_ids": pending_task_ids,
        "project_ids": list(pending_project_ids),
        "pid": None,  # updated after spawn
    }
    meta_path = RUNS_DIR / f"{run_id}.meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Also write to the legacy append-only log
    legacy_log = Path.home() / ".claude" / "workspace" / "supervisor.log"
    cmd = [
        "claude", "--print", "--dangerously-skip-permissions",
        "--agent", "workspace-supervisor",
        f"Your run ID is {run_id}. When updating each task, also preserve its run_id field set to \"{run_id}\". "
        "Process all pending tasks in ~/.claude/workspace/registry.json",
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    out = open(log_path, "w")
    out.write(f"--- supervisor run {run_id} started {datetime.now().isoformat()} ---\n")
    out.flush()
    # Also append to legacy log
    with open(legacy_log, "a") as lf:
        lf.write(f"\n--- supervisor spawn {datetime.now().isoformat()} run_id={run_id} ---\n")
    proc = subprocess.Popen(cmd, stdout=out, stderr=out, text=True, env=env, cwd=str(Path.home()))

    # Update meta with PID
    meta["pid"] = proc.pid
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return (proc, run_id)


def _list_runs() -> list:
    """List all supervisor runs sorted by timestamp desc."""
    if not RUNS_DIR.exists():
        return []
    runs = []
    for meta_path in sorted(RUNS_DIR.glob("*.meta.json"), reverse=True):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            run_id = meta.get("run_id", meta_path.stem.replace(".meta", ""))
            log_path = RUNS_DIR / f"{run_id}.log"
            log_size = log_path.stat().st_size if log_path.exists() else 0
            # Check if process is still running
            pid = meta.get("pid")
            running = False
            if pid:
                try:
                    os.kill(pid, 0)
                    running = True
                except (OSError, ProcessLookupError):
                    pass
            runs.append({
                "run_id": run_id,
                "started_at": meta.get("started_at", ""),
                "task_ids": meta.get("task_ids", []),
                "project_ids": meta.get("project_ids", []),
                "log_size": log_size,
                "running": running,
                "pid": pid,
            })
        except (json.JSONDecodeError, Exception):
            pass
    return runs


def _get_run(run_id: str) -> dict:
    """Get a single run's log and meta."""
    meta_path = RUNS_DIR / f"{run_id}.meta.json"
    log_path = RUNS_DIR / f"{run_id}.log"
    if not meta_path.exists():
        return {"error": "Run not found"}
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception:
        meta = {}
    log_content = ""
    if log_path.exists():
        log_content = log_path.read_text(errors="replace")
    pid = meta.get("pid")
    running = False
    if pid:
        try:
            os.kill(pid, 0)
            running = True
        except (OSError, ProcessLookupError):
            pass
    return {"run_id": run_id, "log": log_content, "meta": meta, "running": running}


def _find_task_run(task_id: str) -> dict:
    """Find the most recent run that includes a given task."""
    if not RUNS_DIR.exists():
        return {"error": "No runs found"}
    for meta_path in sorted(RUNS_DIR.glob("*.meta.json"), reverse=True):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            if task_id in meta.get("task_ids", []):
                return _get_run(meta["run_id"])
        except Exception:
            pass
    return {"error": "No run found for this task"}


# ── HTTP Handler ───────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path):
        ext = path.suffix.lower()
        mime = {".html": "text/html", ".js": "application/javascript", ".css": "text/css"}.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        parts = path.split("/")  # ['', 'api', 'projects', ...]

        # GET /api/registry
        if path == "/api/registry":
            self.send_json(read_registry())
            return

        # Routes under /api/projects/
        if len(parts) >= 4 and parts[1] == "api" and parts[2] == "projects":
            project_id = parts[3]
            registry = read_registry()
            project = get_project(registry, project_id)

            # GET /api/projects/{id}
            if len(parts) == 4:
                if not project:
                    self.send_json({"error": "Not found"}, 404)
                else:
                    self.send_json(project)
                return

            # GET /api/projects/{id}/{sub}
            if len(parts) == 5:
                if not project:
                    self.send_json({"error": "Not found"}, 404)
                    return
                sub = parts[4]
                if sub == "log":
                    self.send_json(read_log(project_id))
                elif sub == "docs":
                    self.send_json(scan_docs(project))
                elif sub == "doc":
                    qs = parse_qs(parsed.query)
                    rel = qs.get("file", [""])[0]
                    self.send_json(read_doc_file(project, rel))
                elif sub == "tree":
                    self.send_json(build_tree(project))
                elif sub == "session":
                    self.send_json(scan_sessions(project, project_id))
                elif sub == "context":
                    self.send_json({"content": read_context_md(project_id)})
                elif sub == "activity-sessions":
                    store = EventStore()
                    proj_path = project.get("path", "")
                    self.send_json(store.get_sessions_summary(project_path=proj_path))
                else:
                    self.send_json({"error": "Not found"}, 404)
                return

        # GET /api/supervisor/runs
        if path == "/api/supervisor/runs":
            self.send_json(_list_runs())
            return

        # GET /api/supervisor/runs/{run_id}
        if len(parts) == 5 and parts[1] == "api" and parts[2] == "supervisor" and parts[3] == "runs":
            run_id = parts[4]
            result = _get_run(run_id)
            if "error" in result:
                self.send_json(result, 404)
            else:
                self.send_json(result)
            return

        # GET /api/tasks/{project_id}/{task_id}/log
        if len(parts) == 6 and parts[1] == "api" and parts[2] == "tasks" and parts[5] == "log":
            task_id = parts[4]
            result = _find_task_run(task_id)
            if "error" in result:
                self.send_json(result, 404)
            else:
                self.send_json(result)
            return

        # GET /api/events
        if path == "/api/events":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["200"])[0])
            since = qs.get("since", [None])[0]
            date = qs.get("date", [None])[0]
            store = EventStore()
            if date:
                self.send_json(store.get_events_for_date(date, limit=limit))
            else:
                self.send_json(store.get_all(limit=limit, since=since))
            return

        # GET /api/events/dates
        if path == "/api/events/dates":
            store = EventStore()
            self.send_json(store.get_event_dates())
            return

        # GET /api/events/sessions
        if path == "/api/events/sessions":
            qs = parse_qs(parsed.query)
            project_path = qs.get("project_path", [None])[0]
            store = EventStore()
            self.send_json(store.get_sessions_summary(project_path=project_path))
            return

        # GET /api/events/session/{session_id}/history
        if len(parts) == 6 and parts[1] == "api" and parts[2] == "events" and parts[3] == "session" and parts[5] == "history":
            sid = parts[4]
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["500"])[0])
            store = EventStore()
            self.send_json(store.get_session_history(sid, limit=limit))
            return

        # GET /api/events/session/{session_id}
        if len(parts) == 5 and parts[1] == "api" and parts[2] == "events" and parts[3] == "session":
            sid = parts[4]
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["200"])[0])
            store = EventStore()
            self.send_json(store.get_session(sid, limit=limit))
            return

        # GET /api/events/stream (SSE)
        if path == "/api/events/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            store = EventStore()
            q = store.subscribe()
            try:
                while True:
                    try:
                        data = q.get(timeout=30)
                        self.wfile.write(f"data: {data}\n\n".encode())
                        self.wfile.flush()
                    except queue.Empty:
                        # Send keepalive
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                store.unsubscribe(q)
            return

        # Static files
        if path == "/" or path == "/index.html":
            file_path = DASHBOARD_DIR / "index.html"
        else:
            file_path = DASHBOARD_DIR / path.lstrip("/")

        if file_path.exists() and file_path.is_file():
            self.send_file(file_path)
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}

        parts = path.split("/")

        # POST /api/webhook/event — receive hook events (backward compat, writes to file)
        if path == "/api/webhook/event":
            store = EventStore()
            if isinstance(data, list):
                for evt in data:
                    store.add(evt)
            else:
                store.add(data)
            self.send_json({"ok": True})
            return

        # POST /api/projects — create new project
        if path == "/api/projects":
            registry = read_registry()
            project_id = next_project_id(registry["projects"])
            ts = now_iso()
            workspace = data.get("workspace", "personal")
            if workspace not in registry["workspaces"]:
                registry["workspaces"].append(workspace)
            project = {
                "id": project_id,
                "name": data.get("name", "Unnamed Project"),
                "workspace": workspace,
                "type": data.get("type", "software"),
                "phase": data.get("phase", "ideation"),
                "path": data.get("path", ""),
                "description": data.get("description", ""),
                "status": "active",
                "created_at": ts,
                "updated_at": ts,
                "tasks": [],
            }
            registry["projects"].append(project)
            write_registry(registry)
            proj_dir = PROJECTS_DIR / project_id
            proj_dir.mkdir(parents=True, exist_ok=True)
            context = f"# {project['name']}\n\nPath: {project['path']}\nDescription: {project['description']}\nCreated: {ts}\n"
            (proj_dir / "context.md").write_text(context)
            self.send_json(project, 201)
            return

        if len(parts) >= 4 and parts[1] == "api" and parts[2] == "projects":
            project_id = parts[3]
            registry = read_registry()
            project = get_project(registry, project_id)
            if not project:
                self.send_json({"error": "Not found"}, 404)
                return

            # POST /api/projects/{id} — update project fields
            if len(parts) == 4:
                for field in ["phase", "status", "description"]:
                    if field in data:
                        project[field] = data[field]
                project["updated_at"] = now_iso()
                write_registry(registry)
                self.send_json(project)
                return

            # POST /api/projects/{id}/tasks — add task
            if len(parts) == 5 and parts[4] == "tasks":
                task_id = next_task_id(registry["projects"])
                ts = now_iso()
                task = {
                    "id": task_id,
                    "title": data.get("title", "Untitled Task"),
                    "type": data.get("type", "other"),
                    "status": "pending",
                    "priority": data.get("priority", "medium"),
                    "agent_spawned": None,
                    "result": None,
                    "blocked_reason": None,
                    "created_at": ts,
                }
                project["tasks"].append(task)
                project["updated_at"] = ts
                write_registry(registry)
                # Auto-trigger supervisor for the new task
                try:
                    proc, run_id = _spawn_supervisor()
                except Exception:
                    pass  # Non-blocking — task is already saved
                self.send_json(task, 201)
                return

        # POST /api/supervisor/run
        if path == "/api/supervisor/run":
            try:
                proc, run_id = _spawn_supervisor()
                self.send_json({"status": "started", "pid": proc.pid, "run_id": run_id, "ts": now_iso()})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        self.send_json({"error": "Not found"}, 404)


def main():
    # Initialize EventStore on startup (loads events, builds session index, starts file watcher)
    EventStore()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    server.daemon_threads = True
    print(f"AI Workspace OS Dashboard")
    print(f"  http://localhost:{PORT}")
    print(f"  Registry: {REGISTRY_PATH}")
    print(f"  Events:   {EVENTS_DIR}")
    print(f"  Sessions: {SESSIONS_INDEX}")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
