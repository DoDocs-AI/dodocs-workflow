"""Run lifecycle: request, queue, start within limits, cancel."""
from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import time
import uuid
from typing import Optional

from . import agterm, paths, store

ACTIVE_STATES = ("running", "blocked")
FINISHED_STATES = ("done", "failed", "interrupted", "cancelled")

RESULT_NOTE_SUFFIX = (
    "When this work is finished, or you cannot continue, write a short result note to %s. "
    "First line: exactly DONE, BLOCKED or FAILED. Then: what was done, the pull request URL "
    "if any, and what is left. Write this file even if the work failed."
)


class RunRefused(Exception):
    """The run cannot be started; the message is for the owner."""


class RunError(Exception):
    pass


def _moved(run: dict, now: float, **fields) -> dict:
    """A copy of `run` with `fields` applied and the state-change time stamped."""
    return {**run, **fields, "state_changed_at": now}


def new_run_id() -> str:
    return "r-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), secrets.token_hex(2))


def counts_against_total(run: dict) -> bool:
    if run.get("state") not in ACTIVE_STATES:
        return False
    if run.get("state") == "blocked" and str(run.get("reason") or "").startswith("awaiting approval"):
        return False
    return True


# -- preflight ------------------------------------------------------------


def _out_of_checkout_reason(command: str) -> Optional[str]:
    tokens = command.split()
    if tokens and tokens[0].lstrip("/").split(":")[-1] == "container-team" and tokens[0].startswith("/"):
        return "/container-team"
    for tok in tokens:
        if tok == "--docker" or tok.startswith("--docker="):
            return "--docker"
    return None


def _claude_state_path() -> str:
    return os.environ.get("DW_CLAUDE_STATE") or os.path.join(os.path.expanduser("~"), ".claude.json")


def project_trusted(project_path: str) -> bool:
    """True when Claude Code already accepted its workspace-trust dialog for this exact path.

    Claude Code records that as projects[<abs path>].hasTrustDialogAccepted in ~/.claude.json.
    Read-only; any unreadable or unexpected file counts as not trusted.
    """
    try:
        with open(_claude_state_path()) as fh:
            state = json.load(fh)
        entries = state["projects"]
        wanted = os.path.realpath(project_path)
        for key, value in entries.items():
            if isinstance(value, dict) and value.get("hasTrustDialogAccepted") is True \
                    and os.path.realpath(key) == wanted:
                return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return False


def _preflight(project: dict, command: str) -> None:
    harness = project.get("harness")
    if harness != "claude":
        raise RunRefused("project %s uses harness %r; only claude is supported" % (project["id"], harness))
    if not command.strip():
        raise RunRefused("empty command")
    bad = _out_of_checkout_reason(command)
    if bad:
        raise RunRefused(
            "%s works outside the project checkout, where dw's approval guard cannot reach it; "
            "run it by hand instead" % bad)
    if not project_trusted(project["path"]):
        raise RunRefused(
            "Claude Code has not trusted %s yet; open Claude Code once in that directory "
            "and accept the trust dialog" % project["path"])
    if not agterm.available():
        raise RunRefused("AGTerm is not reachable (is the app running and agtermctl installed?)")


# -- launching ------------------------------------------------------------


def _session_command(run_id: str, harness_session: str, resume: bool = False) -> str:
    claude = os.environ.get("DW_CLAUDE") or "claude"
    head = "DW_RUN_ID=%s %s --permission-mode bypassPermissions" % (run_id, shlex.quote(claude))
    if resume:
        inner = "%s --resume %s" % (head, harness_session)
    else:
        inner = "%s --session-id %s \"$(cat %s)\"" % (
            head, harness_session, shlex.quote(os.path.abspath(str(paths.prompt_path(run_id)))))
    return "zsh -lc " + shlex.quote(inner)


def _write_prompt(run_id: str, command: str) -> None:
    note = os.path.abspath(str(paths.result_note_path(run_id)))
    text = command + "\n\n" + RESULT_NOTE_SUFFIX % note
    path = paths.prompt_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _session_name(project: dict, command: str) -> str:
    return "%s: %s" % (project["name"], re.sub(r"\s+", " ", command).strip()[:40])


def _start(run: dict, project: dict) -> dict:
    """Launch a queued run. Only a record that is still `queued` may become `running`."""
    run_id = run["id"]
    if store.load_run(run_id).get("state") != "queued":
        raise RunError("run %s is no longer queued" % run_id)
    harness_session = str(uuid.uuid4())
    _write_prompt(run_id, run["command"])
    sid = agterm.new_session(
        cwd=project["path"], workspace_name=project["group"],
        name=_session_name(project, run["command"]),
        command=_session_command(run_id, harness_session), context=run_id)
    now = time.time()

    def mark(r):
        if r.get("state") != "queued":
            raise RunError("run %s is no longer queued" % run_id)
        return _moved(r, now, state="running", reason=None, agterm_session=sid,
                      harness_session=harness_session, started_at=now)

    try:
        return store.update_run(run_id, mark)
    except RunError:
        try:  # cancelled while launching: do not leave its session behind
            agterm.close_session(sid)
        except agterm.AgtermError:
            pass
        raise


def _set_reason(run_id: str, reason: str) -> None:
    def setter(r):
        return {**r, "reason": reason} if r.get("state") == "queued" else r

    store.update_run(run_id, setter)


def _fail_queued(run_id: str, reason: str) -> None:
    now = time.time()

    def fail(r):
        if r.get("state") != "queued":
            return r
        return _moved(r, now, state="failed", reason=reason, ended_at=now)

    store.update_run(run_id, fail)


def _usage(records: list) -> tuple:
    """(active runs per project, runs counting against the total)."""
    per_project: dict = {}
    total = 0
    for r in records:
        if r.get("state") in ACTIVE_STATES:
            per_project[r["project_id"]] = per_project.get(r["project_id"], 0) + 1
        if counts_against_total(r):
            total += 1
    return per_project, total


def _limit_reason(per_project: dict, total: int, pid: str, per_limit: int,
                  total_limit: int) -> Optional[str]:
    if per_project.get(pid, 0) >= per_limit:
        return "project busy"
    if total >= total_limit:
        return "total limit %d" % total_limit
    return None


def start_eligible() -> list:
    """Start queued runs oldest-first while the limits allow; returns the runs started."""
    started: list = []
    with store.file_lock(paths.home() / "start.lock"):
        registry = store.load_registry()
        limits = registry.get("limits", {})
        per_limit = int(limits.get("per_project", 1))
        total_limit = int(limits.get("total", 3))
        records, _corrupt = store.list_runs()
        per_project, total = _usage(records)
        queued = sorted((r for r in records if r.get("state") == "queued"),
                        key=lambda r: (r.get("created_at") or 0, r["id"]))
        projects = {p["id"]: p for p in registry.get("projects", [])}
        for run in queued:
            pid = run["project_id"]
            project = projects.get(pid)
            if project is None:
                _fail_queued(run["id"], "project removed from registry")
                continue
            reason = _limit_reason(per_project, total, pid, per_limit, total_limit)
            if reason:
                if run.get("reason") != reason:
                    _set_reason(run["id"], reason)
                continue
            try:
                started.append(_start(run, project))
            except RunError:
                continue  # no longer queued (cancelled meanwhile)
            except agterm.AgtermUnavailable:
                _set_reason(run["id"], "AGTerm unavailable")
                break
            except agterm.AgtermError as exc:
                _fail_queued(run["id"], "launch failed: %s" % (str(exc) or "unknown error")[:300])
                continue
            per_project[pid] = per_project.get(pid, 0) + 1
            total += 1
    return started


def request_run(project: dict, command: str) -> dict:
    """Validate, record the run as queued, then start whatever the limits allow."""
    _preflight(project, command)
    record = {
        "id": new_run_id(), "project_id": project["id"], "command": command,
        "state": "queued", "reason": None, "agterm_session": None,
        "harness_session": None, "created_at": time.time(), "started_at": None,
        "ended_at": None, "approvals": [], "pending_approval": None, "grants": [],
    }
    store.create_run(record)
    start_eligible()
    return store.load_run(record["id"])


def cancel_run(run_id: str) -> dict:
    with store.file_lock(paths.home() / "start.lock"):
        try:
            run = store.load_run(run_id)
        except store.RunNotFound:
            raise RunError("unknown run: %s" % run_id)
        if run["state"] in FINISHED_STATES:
            raise RunError("run %s is already %s" % (run_id, run["state"]))
        if run["state"] in ACTIVE_STATES and run.get("agterm_session"):
            try:
                agterm.close_session(run["agterm_session"])
            except agterm.AgtermUnavailable:
                raise RunError("AGTerm is not reachable; cannot close the session of %s" % run_id)
            except agterm.AgtermError:
                pass  # session is already gone
        now = time.time()

        def cancel(r):
            if r.get("state") in FINISHED_STATES:
                raise RunError("run %s is already %s" % (run_id, r["state"]))
            return _moved(r, now, state="cancelled", reason="cancelled by owner", ended_at=now)

        cancelled = store.update_run(run_id, cancel)
    start_eligible()
    return cancelled


def finish_run_changed(run_id: str, state: str, reason: Optional[str]) -> tuple:
    """Move an active run to `state`; returns (record, changed). A run that is not
    running or blocked (queued, or already finished) is left exactly as it is."""
    if state not in ("done", "failed", "interrupted"):
        raise ValueError("cannot finish a run as %r" % state)
    now = time.time()
    changed = []

    def finish(r):
        if r.get("state") not in ACTIVE_STATES:
            return r
        changed.append(True)
        return _moved(r, now, state=state, reason=reason, ended_at=now)

    record = store.update_run(run_id, finish)
    return record, bool(changed)


def finish_run(run_id: str, state: str, reason: Optional[str]) -> dict:
    return finish_run_changed(run_id, state, reason)[0]


def dismiss_run(run_id: str) -> dict:
    """Acknowledge a finished run so it no longer asks for the owner's attention."""
    def dismiss(r):
        if r.get("state") not in FINISHED_STATES:
            raise RunError("run %s is %s, not finished" % (run_id, r.get("state")))
        return {**r, "acknowledged": True, "acknowledged_at": time.time()}

    try:
        return store.update_run(run_id, dismiss)
    except store.RunNotFound:
        raise RunError("unknown run: %s" % run_id)


def resume_run(run_id: str) -> dict:
    """Reopen an interrupted run in a new AGTerm session that resumes its Claude conversation."""
    with store.file_lock(paths.home() / "start.lock"):
        try:
            run = store.load_run(run_id)
        except store.RunNotFound:
            raise RunError("unknown run: %s" % run_id)
        if run.get("state") != "interrupted":
            raise RunError("run %s is %s; only an interrupted run can be resumed"
                           % (run_id, run.get("state")))
        harness_session = run.get("harness_session")
        if not harness_session:
            raise RunRefused("run %s has no recorded Claude session to resume" % run_id)
        registry = store.load_registry()
        project = next((p for p in registry.get("projects", []) if p["id"] == run["project_id"]), None)
        if project is None:
            raise RunRefused("project %s is no longer in the registry" % run["project_id"])
        _preflight(project, run["command"])
        limits = registry.get("limits", {})
        per_project, total = _usage(store.list_runs()[0])
        reason = _limit_reason(per_project, total, project["id"],
                               int(limits.get("per_project", 1)), int(limits.get("total", 3)))
        if reason:
            raise RunRefused("cannot resume %s now: %s" % (run_id, reason))
        sid = agterm.new_session(
            cwd=project["path"], workspace_name=project["group"],
            name=_session_name(project, run["command"]),
            command=_session_command(run_id, harness_session, resume=True), context=run_id)
        now = time.time()

        def mark(r):
            if r.get("state") != "interrupted":
                raise RunError("run %s is no longer interrupted" % run_id)
            moved = _moved(r, now, state="running", reason=None, agterm_session=sid, ended_at=None)
            moved.pop("acknowledged", None)
            moved.pop("acknowledged_at", None)
            return moved

        try:
            return store.update_run(run_id, mark)
        except RunError:
            try:
                agterm.close_session(sid)
            except agterm.AgtermError:
                pass
            raise
