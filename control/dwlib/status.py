"""Read-only merged status across projects. Never writes a run record, the registry or AGTerm."""
from __future__ import annotations

import glob
import os
from typing import Optional

from . import agterm, paths, store

ACTIVE = ("running", "blocked")
ENDED = ("done", "failed", "interrupted", "cancelled")
NEEDS_OWNER = ("blocked", "failed", "interrupted")
RECENT_LIMIT = 5
RESULT_LINES = 20
DEFAULT_STALL_MINUTES = 30


def _section(text: str, heading: str) -> Optional[str]:
    lines = text.splitlines()
    out: Optional[list] = None
    for line in lines:
        if out is None:
            if line.strip().lower() == "## " + heading.lower():
                out = [line.rstrip()]
        elif line.startswith("## "):
            break
        else:
            out.append(line.rstrip())
    if out is None:
        return None
    return "\n".join(out).rstrip()


def find_progress(project_path: str, run: dict) -> Optional[str]:
    """Current phase and phase table from the newest PROGRESS.md written since the run started."""
    command = str(run.get("command") or "").lstrip()
    if command.split(None, 1)[:1] != ["/scrum-team"]:
        return None
    started = run.get("started_at")
    if started is None:
        return None
    newest, newest_mtime = None, None
    for candidate in glob.glob(os.path.join(project_path, "docs", "features", "*", "PROGRESS.md")):
        try:
            mtime = os.path.getmtime(candidate)
        except OSError:
            continue
        if mtime > started and (newest_mtime is None or mtime > newest_mtime):
            newest, newest_mtime = candidate, mtime
    if newest is None:
        return None
    try:
        with open(newest, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    parts = [s for s in (_section(text, "Current Phase"), _section(text, "Phase Status")) if s]
    return "\n\n".join(parts) if parts else None


def _result_note(run_id: str) -> Optional[str]:
    candidates = [paths.result_note_path(run_id)] + paths.blocked_note_paths(run_id)
    lines = None
    for candidate in candidates:
        try:
            with open(str(candidate), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
            break
        except OSError:
            continue
    if lines is None:
        return None
    text = "\n".join(lines[:RESULT_LINES]).rstrip()
    return text or None


def _since(run: dict, now: float) -> Optional[float]:
    state = run.get("state")
    ref = run.get("state_changed_at")
    if ref is None:
        if state in ENDED:
            ref = run.get("ended_at")
        elif state in ACTIVE:
            ref = run.get("started_at")
        else:
            ref = run.get("created_at")
    if ref is None:
        ref = run.get("created_at")
    return max(0.0, now - ref) if ref is not None else None


def _acknowledged(run: dict) -> bool:
    if run.get("acknowledged") is not True:
        return False
    at, changed = run.get("acknowledged_at"), run.get("state_changed_at")
    if at is None or changed is None:
        return at is not None or changed is None
    return at >= changed


def _run_view(project: dict, run: dict, sessions: Optional[dict], now: float,
              stall_minutes: float) -> dict:
    state = run.get("state")
    live = None
    session_missing = False
    stalled = False
    if sessions is not None and state in ACTIVE and run.get("agterm_session"):
        session = sessions.get(run["agterm_session"])
        if session is None:
            session_missing = state == "running"
        else:
            live = session.get("status")
            changed = session.get("status_changed_at")
            stalled = (state == "running" and live == "active" and changed is not None
                       and now - changed > stall_minutes * 60)
    return {
        "id": run["id"],
        "command": run.get("command"),
        "state": state,
        "reason": run.get("reason"),
        "since": _since(run, now),
        "live": live,
        "stalled": stalled,
        "session_missing": session_missing,
        "progress": find_progress(project["path"], run) if state in ACTIVE else None,
        "result": _result_note(run["id"]) if state in ENDED or state == "blocked" else None,
    }


def project_status(project: dict, runs: list, sessions: Optional[dict], now: float,
                   stall_minutes: float = DEFAULT_STALL_MINUTES) -> dict:
    mine = [r for r in runs if r.get("project_id") == project["id"]]

    def view(r):
        return _run_view(project, r, sessions, now, stall_minutes)

    active = sorted((r for r in mine if r.get("state") in ACTIVE),
                    key=lambda r: (r.get("started_at") or 0, r["id"]))
    queued = sorted((r for r in mine if r.get("state") == "queued"),
                    key=lambda r: (r.get("created_at") or 0, r["id"]))
    ended = sorted((r for r in mine if r.get("state") in ENDED),
                   key=lambda r: (r.get("ended_at") or r.get("created_at") or 0, r["id"]),
                   reverse=True)[:RECENT_LIMIT]
    return {"project": project["id"], "active": [view(r) for r in active],
            "queued": [view(r) for r in queued], "recent": [view(r) for r in ended]}


def overall_status(now: float) -> dict:
    registry = store.load_registry()
    records, corrupt = store.list_runs()
    try:
        sessions: Optional[dict] = agterm.session_states()
    except agterm.AgtermError:
        sessions = None
    stall = registry.get("stall_minutes", DEFAULT_STALL_MINUTES)
    try:
        stall = float(stall)
    except (TypeError, ValueError):
        stall = DEFAULT_STALL_MINUTES
    projects = [project_status(p, records, sessions, now, stall) for p in registry.get("projects", [])]
    by_id = {p["id"]: p for p in registry.get("projects", [])}
    needs_owner = []
    for r in sorted(records, key=lambda r: (r.get("created_at") or 0, r["id"])):
        if r.get("state") in NEEDS_OWNER and not _acknowledged(r):
            project = by_id.get(r.get("project_id")) or {"id": r.get("project_id"), "path": ""}
            needs_owner.append({**_run_view(project, r, sessions, now, stall),
                                "project": r.get("project_id")})
    return {"needs_owner": needs_owner, "projects": projects,
            "corrupt_files": [str(p) for p in corrupt],
            "agterm_reachable": sessions is not None}
