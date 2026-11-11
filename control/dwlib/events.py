"""Run state changes driven by AGTerm events (called from `dw hook ...`)."""
from __future__ import annotations

import time
from typing import Optional

from . import agterm, paths, runs, store

MARKERS = ("DONE", "BLOCKED", "FAILED")
REASON_CHARS = 200


def log_error(event: str, exc: BaseException) -> None:
    """Append one line to $DW_HOME/dw.log. Never raises."""
    try:
        path = paths.home() / "dw.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        message = " ".join(str(exc).split()) or exc.__class__.__name__
        with open(str(path), "a") as fh:
            fh.write("%s %s: %s: %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), event,
                                          exc.__class__.__name__, message))
    except Exception:
        pass


def read_result_note(run_id: str) -> Optional[tuple]:
    """(DONE|BLOCKED|FAILED, body) from the run's result note; None when absent or empty."""
    try:
        with open(str(paths.result_note_path(run_id)), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    if not text.strip():
        return None
    first, _, rest = text.strip().partition("\n")
    marker = first.strip().upper()
    if marker in MARKERS:
        return marker, rest.strip()
    return "DONE", text.strip()


def _find_active_run(session_id: str) -> Optional[dict]:
    for record in store.list_runs()[0]:
        if record.get("agterm_session") == session_id and record.get("state") in runs.ACTIVE_STATES:
            return record
    return None


def _first_line(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.strip():
            return line.strip()[:REASON_CHARS]
    return fallback


def _notify(event: str, session_id: str, title: str, body: str) -> None:
    try:
        agterm.notify(session_id, title, body)
    except Exception as exc:  # a lost notification must not undo or block the state change
        log_error(event + " notify", exc)


def _block(run_id: str, reason: str) -> bool:
    """running -> blocked. A pending approval keeps its reason. True when this call changed it."""
    now = time.time()
    changed = []

    def block(r):
        if r.get("state") != "running":
            return r
        changed.append(True)
        if r.get("pending_approval"):
            return runs._moved(r, now, state="blocked")
        return runs._moved(r, now, state="blocked", reason=reason)

    record = store.update_run(run_id, block)
    return bool(changed) and not record.get("pending_approval")


def _unblock(run_id: str) -> None:
    now = time.time()

    def unblock(r):
        if r.get("state") != "blocked" or r.get("pending_approval"):
            return r
        return runs._moved(r, now, state="running", reason=None)

    store.update_run(run_id, unblock)


def _finish_from_note(run: dict, note: tuple, session_id: str, event: str) -> None:
    marker, body = note
    run_id = run["id"]
    if marker == "BLOCKED":
        reason = "blocked: " + _first_line(body, "see result note")
        if _block(run_id, reason):
            _notify(event, session_id, "dw: %s needs you" % run_id, reason)
        return
    if marker == "FAILED":
        state, reason = "failed", _first_line(body, "see result note")
    else:
        state, reason = "done", None
    _, changed = runs.finish_run_changed(run_id, state, reason)
    if changed:
        _notify(event, session_id, "dw: %s %s" % (run_id, state), _first_line(body, state))


def on_status(session_id: str, status: str) -> None:
    run = _find_active_run(session_id)
    if run is None:
        return
    run_id = run["id"]
    if status == "blocked":
        if _block(run_id, "waiting for input"):
            _notify("status blocked", session_id, "dw: %s is waiting" % run_id, "waiting for input")
    elif status == "active":
        _unblock(run_id)
    elif status == "completed":
        note = read_result_note(run_id)
        if note is None:
            return
        try:
            _finish_from_note(run, note, session_id, "status completed")
        finally:
            runs.start_eligible()


def on_session_closed(session_id: str) -> None:
    run = _find_active_run(session_id)
    if run is None:
        return
    try:
        note = read_result_note(run["id"])
        if note is not None and note[0] == "FAILED":
            runs.finish_run(run["id"], "failed", _first_line(note[1], "see result note"))
        elif note is not None and note[0] == "DONE":
            runs.finish_run(run["id"], "done", None)
        else:
            reason = "session closed before the work finished"
            if note is not None:
                reason = "session closed while blocked: " + _first_line(note[1], "see result note")
            runs.finish_run(run["id"], "interrupted", reason)
    finally:
        runs.start_eligible()
