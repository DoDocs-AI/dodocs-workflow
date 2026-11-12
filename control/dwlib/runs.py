"""Run lifecycle: request, queue, start within limits, cancel."""
from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Optional

from . import agterm, paths, store

ACTIVE_STATES = ("running", "blocked")
FINISHED_STATES = ("done", "failed", "interrupted", "cancelled")

RESULT_NOTE_SUFFIX = (
    "When this work is finished, or you cannot continue, write a short result note to %s. "
    "First line: exactly DONE, BLOCKED or FAILED. Then: what was done, the pull request URL "
    "if any, and what is left. Write this file even if the work failed. Write it with your "
    "file-writing tool, or with a single `cat > <path> <<'EOF' ... EOF` or `printf ... > <path>` "
    "to exactly that path; the file already exists."
)


RESUME_PROMPT = "You were interrupted. Continue the task from where it stopped and finish it."


class RunRefused(Exception):
    """The run cannot be started; the message is for the owner."""


class RunError(Exception):
    pass


def _moved(run: dict, now: float, **fields) -> dict:
    """A copy of `run` with `fields` applied and the state-change time stamped."""
    return {**run, **fields, "state_changed_at": now}


def _clear_approvals(run: dict) -> dict:
    """Drop the pending approval and one-shot grants; `approvals` already granted are kept."""
    return {**run, "pending_approval": None, "grants": []}


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


GUARD_PROBE_TIMEOUT = 10  # seconds


def _guard_entry_problem(argv: list) -> Optional[str]:
    """Run the settings file's guard entry once, without a shell, on a harmless call (a `Read`
    in a fresh temp directory no project contains) and without `DW_RUN_ID`; a healthy guard
    allows it silently. Returns what went wrong, or None."""
    probe_dir = tempfile.mkdtemp(prefix="dw-guard-probe-")
    try:
        payload = {"session_id": "dw-preflight", "cwd": probe_dir,
                   "hook_event_name": "PreToolUse", "tool_name": "Read",
                   "tool_input": {"file_path": os.path.join(probe_dir, "probe.txt")},
                   "tool_use_id": "dw-preflight"}
        env = {k: v for k, v in os.environ.items() if k != "DW_RUN_ID"}
        try:
            done = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                                  env=env, cwd=probe_dir, timeout=GUARD_PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return "it did not answer within %d s" % GUARD_PROBE_TIMEOUT
        except OSError as exc:
            return "it cannot be started (%s)" % (exc.strerror or exc.__class__.__name__)
        if done.returncode != 0:
            return "it exited with status %d" % done.returncode
        if done.stdout:
            return "it printed a decision for a harmless call"
        return None
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def _preflight(project: dict, command: str) -> None:
    from . import guard  # guard imports this module

    settings = guard.settings_path()
    argv = guard.guard_entry_argv(settings)
    if argv is None and guard.guard_entry_narrow(settings):
        raise RunRefused("the approval guard entry in %s does not cover all tools (its matcher "
                         "leaves some out); run `dw setup` to replace it" % settings)
    if argv is None:
        raise RunRefused("the approval guard is not installed in %s; run `dw setup` first" % settings)
    problem = _guard_entry_problem(argv)
    if problem:
        raise RunRefused("the approval guard entry in %s does not work: %s; run `dw setup` again"
                         % (settings, problem))
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
        # The prompt is an ordinary positional argument after --resume; without one the
        # reopened conversation waits at its input line.
        inner = "%s --resume %s \"$(cat %s)\"" % (
            head, harness_session,
            shlex.quote(os.path.abspath(str(paths.resume_prompt_path(run_id)))))
    else:
        inner = "%s --session-id %s \"$(cat %s)\"" % (
            head, harness_session, shlex.quote(os.path.abspath(str(paths.prompt_path(run_id)))))
    return "zsh -lc " + shlex.quote(inner)


def _write_prompt(run_id: str, command: str, resume: bool = False) -> None:
    """The first prompt, in a file (never inline): the run's command, or for a resume the
    fixed sentence that makes the conversation go on; then the result-note instructions."""
    note = os.path.abspath(str(paths.result_note_path(run_id)))
    text = (RESUME_PROMPT if resume else command) + "\n\n" + RESULT_NOTE_SUFFIX % note
    path = paths.resume_prompt_path(run_id) if resume else paths.prompt_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def create_empty_note(run_id: str) -> None:
    """The run's result note as an empty regular file (mode 0600) when there is none: an empty
    note means no note yet, and the guard spares writes only to a note that exists."""
    path = str(paths.result_note_path(run_id))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    os.close(fd)


def set_aside_note(run_id: str) -> None:
    """Move the run's result note out of the way (runs/<id>.result.blocked-<stamp>.md), so it
    is acted on only once; then an empty note takes its place."""
    source = paths.result_note_path(run_id)
    stamp = int(time.time())
    while True:
        target = paths.runs_dir() / ("%s.result.blocked-%d.md" % (run_id, stamp))
        if not target.exists():
            break
        stamp += 1
        if stamp > time.time() + 10:
            raise OSError("no free name for the moved-aside note")
    os.rename(str(source), str(target))
    create_empty_note(run_id)


def _note_written(run_id: str) -> bool:
    try:
        with open(str(paths.result_note_path(run_id)), encoding="utf-8", errors="replace") as fh:
            return bool(fh.read().strip())
    except OSError:
        return False


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


def request_run(project: dict, command: str, keep_open: bool = False) -> dict:
    """Validate, record the run as queued, then start whatever the limits allow. With
    `keep_open`, the run's session is not closed when it finishes as done."""
    _preflight(project, command)
    record = {
        "id": new_run_id(), "project_id": project["id"], "project_path": project["path"],
        "command": command,
        "state": "queued", "reason": None, "agterm_session": None,
        "harness_session": None, "created_at": time.time(), "started_at": None,
        "ended_at": None, "approvals": [], "pending_approval": None, "grants": [],
    }
    if keep_open:
        record["keep_open"] = True
    store.create_run(record)
    create_empty_note(record["id"])
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
            return _clear_approvals(
                _moved(r, now, state="cancelled", reason="cancelled by owner", ended_at=now))

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
        return _clear_approvals(_moved(r, now, state=state, reason=reason, ended_at=now))

    record = store.update_run(run_id, finish)
    return record, bool(changed)


def finish_run(run_id: str, state: str, reason: Optional[str]) -> dict:
    return finish_run_changed(run_id, state, reason)[0]


def closes_when_done(run: dict) -> bool:
    """Whether a run's session is closed when it finishes as done: not when the run was
    started with --keep-open, nor when the registry's `close_done_sessions` is false."""
    if run.get("keep_open"):
        return False
    try:
        return store.load_registry().get("close_done_sessions", True) is not False
    except store.CorruptFile:
        return False


def dismiss_run(run_id: str) -> dict:
    """Acknowledge a finished run so it no longer asks for the owner's attention, and close its
    session if it is still open (best effort; `session_closed` in the result says so)."""
    def dismiss(r):
        if r.get("state") not in FINISHED_STATES:
            raise RunError("run %s is %s, not finished" % (run_id, r.get("state")))
        return {**r, "acknowledged": True, "acknowledged_at": time.time()}

    try:
        record = store.update_run(run_id, dismiss)
    except store.RunNotFound:
        raise RunError("unknown run: %s" % run_id)
    closed = False
    sid = record.get("agterm_session")
    if sid:
        try:
            sessions, _windows = agterm.session_snapshot()
        except agterm.AgtermError:
            sessions = {}  # AGTerm unreachable: acknowledged all the same
        if sid in sessions:
            try:
                agterm.close_session(sid)
                closed = True
            except agterm.AgtermError as exc:
                from .events import log_error  # events imports this module
                log_error("dismiss close session", exc)
    return {**record, "session_closed": closed}


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
        if _note_written(run_id):
            set_aside_note(run_id)  # a note from before the interruption must not end the run
        create_empty_note(run_id)
        _write_prompt(run_id, run["command"], resume=True)
        sid = agterm.new_session(
            cwd=project["path"], workspace_name=project["group"],
            name=_session_name(project, run["command"]),
            command=_session_command(run_id, harness_session, resume=True), context=run_id)
        now = time.time()

        def mark(r):
            if r.get("state") != "interrupted":
                raise RunError("run %s is no longer interrupted" % run_id)
            moved = _clear_approvals(
                _moved(r, now, state="running", reason=None, agterm_session=sid, ended_at=None))
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
