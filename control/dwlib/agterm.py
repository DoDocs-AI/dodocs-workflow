"""Thin adapter over `agtermctl`. The only module that spawns it."""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Optional


class AgtermError(Exception):
    pass


class AgtermUnavailable(AgtermError):
    """agtermctl is missing, or the call could not reach AGTerm."""


_CONNECT_RE = re.compile(r"connect|socket|refused|no such file|not running", re.I)


def _binary() -> str:
    return os.environ.get("DW_AGTERMCTL") or "agtermctl"


def _socket() -> Optional[str]:
    return os.environ.get("AGT_SOCKET") or os.environ.get("AGTERM_SOCKET") or None


def _timeout(default: Optional[float]) -> Optional[float]:
    override = os.environ.get("DW_AGTERMCTL_TIMEOUT")
    if override and default is not None:
        try:
            return float(override)
        except ValueError:
            pass
    return default


def _run(words: list, options: Optional[list] = None, timeout: Optional[float] = None,
         ok_codes: tuple = (0,), raise_timeout: bool = False):
    """Run `agtermctl <words> [--socket S] <options>`; options go after the subcommand."""
    argv = [_binary()] + list(words)
    sock = _socket()
    if sock:
        argv += ["--socket", sock]
    argv += list(options or [])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if raise_timeout:
            raise
        raise AgtermUnavailable("agtermctl timed out after %ss: %s" % (timeout, " ".join(words)))
    except FileNotFoundError:
        raise AgtermUnavailable("agtermctl not found: %s" % _binary())
    except PermissionError:
        raise AgtermUnavailable("agtermctl is not executable: %s" % _binary())
    if proc.returncode not in ok_codes:
        detail = (proc.stderr or proc.stdout or "").strip()
        if _CONNECT_RE.search(detail):
            raise AgtermUnavailable(detail)
        raise AgtermError(detail or "agtermctl exited %d" % proc.returncode)
    return proc


def _result(proc) -> dict:
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        raise AgtermError("unreadable agtermctl output: %r" % proc.stdout[:200])
    if not isinstance(data, dict):
        raise AgtermError("unexpected agtermctl output")
    if data.get("ok") is False:
        raise AgtermError(str(data.get("error")))
    result = data.get("result", data)
    return result if isinstance(result, dict) else {}


def available() -> bool:
    try:
        _run(["window", "list"], ["--json"], timeout=_timeout(10))
        return True
    except AgtermError:
        return False


def new_session(cwd: str, workspace_name: str, name: str, command: str, context: str) -> str:
    """Start a background session running `command`; returns its session id."""
    proc = _run(["session", "new"], [
        "--no-select", "--workspace-name", workspace_name, "--create-workspace",
        "--cwd", cwd, "--name", name, "--command", command, "--json"], timeout=_timeout(30))
    sid = None
    try:
        sid = _result(proc).get("id")
    except AgtermError:
        sid = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else None
    if not sid:
        raise AgtermError("agtermctl did not return a session id")
    try:
        # A restored session must not re-run the harness; pin the restore to a plain shell.
        _run(["session", "restore"], ["--none", "--target", sid], timeout=_timeout(15))
        _run(["session", "context", context], ["--target", sid], timeout=_timeout(15))
    except AgtermError:
        try:
            close_session(sid)
        except AgtermError:
            pass
        raise
    return sid


def session_states() -> dict:
    """session id -> {status, status_changed_at, name}, across all open windows."""
    windows = _result(_run(["window", "list"], ["--json"], timeout=_timeout(15))).get("windows") or []
    states: dict = {}
    for win in windows:
        if not win.get("open", True):
            continue
        tree = _result(_run(["tree"], ["--json", "--window", str(win["id"])], timeout=_timeout(15)))
        for ws in (tree.get("tree") or {}).get("workspaces") or []:
            for node in ws.get("sessions") or []:
                states[node["id"]] = {
                    "status": node.get("status"),
                    "status_changed_at": node.get("statusChangedAt"),
                    "name": node.get("name"),
                }
    return states


def set_status(session_id: str, status: str) -> None:
    """Set a session's agent status glyph (idle, active, completed, blocked)."""
    options = ["--target", session_id] + (["--blink"] if status == "blocked" else [])
    _run(["session", "status", status], options, timeout=_timeout(15))


def notify(session_id: str, title: str, body: str) -> None:
    _run(["notify", body], ["--title", title, "--target", session_id], timeout=_timeout(15))


def ask(session_id: str, title: str, message: str, buttons: list, timeout: int,
        default: Optional[str] = None) -> Optional[str]:
    """Ask the owner; returns the chosen button id, None on escape, cancel or timeout.
    `default` is the button highlighted at first (what a bare Enter picks)."""
    options = ["--message", message, "--target", session_id]
    if default:
        options += ["--default", default]
    for button_id, label in buttons:
        options += ["--button", "%s=%s" % (button_id, label)]
    try:
        proc = _run(["ask", title], options + ["--json"], timeout=timeout,
                    ok_codes=(0, 2, 3, 124), raise_timeout=True)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        data = data["result"]
    if isinstance(data, dict) and data.get("result") == "answered":
        return data.get("id")
    return None


def close_session(session_id: str) -> None:
    _run(["session", "close"], ["--target", session_id], timeout=_timeout(15))


def session_tail(session_id: str, lines: int) -> str:
    proc = _run(["session", "text"], ["--lines", str(lines), "--target", session_id], timeout=_timeout(15))
    return proc.stdout
