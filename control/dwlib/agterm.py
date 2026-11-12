"""Thin adapter over `agtermctl`. The only module that spawns it."""
from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from typing import Optional


class AgtermError(Exception):
    pass


class AgtermUnavailable(AgtermError):
    """agtermctl is missing, or the call could not reach AGTerm."""


_CONNECT_RE = re.compile(r"connect|socket|refused|no such file|not running", re.I)

# AGTerm refuses free text that carries a control character (newline included) and caps its
# length; every free-text argument goes through `sanitise` with one of these limits.
TITLE_MAX = 120
MESSAGE_MAX = 240
NAME_MAX = 80
_CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _marked_format(text: str) -> str:
    """Unicode format characters (category Cf: bidirectional overrides and isolates, zero-width
    spaces and joiners, byte-order marks...) shown as a visible placeholder: they could
    otherwise make the owner read a different command than the one that runs."""
    return "".join(CONTROL_MARK if unicodedata.category(ch) == "Cf" else ch for ch in text)


def sanitise(text, limit: int) -> str:
    """One line AGTerm accepts: control characters and line or paragraph separators become
    spaces, format characters a visible "?", runs of whitespace collapse, the ends are
    trimmed, and text over `limit` characters ends in an ellipsis."""
    line = " ".join(_marked_format(_CONTROL_RE.sub(" ", str(text))).split())
    return line if len(line) <= limit else line[:limit - 1] + "\u2026"


_LINE_BREAK_RE = re.compile("\r\n|[\n\r\u2028\u2029]")
LINE_BREAK_MARK = "\u23ce"  # RETURN SYMBOL
TAB_MARK = "\u2423"  # OPEN BOX
CONTROL_MARK = "?"


def visible(text) -> str:
    """Text whose line breaks, tabs and other control characters are shown as printable marks
    (which AGTerm accepts), so a command keeps its meaning on one line."""
    line = _LINE_BREAK_RE.sub(LINE_BREAK_MARK, str(text)).replace("\t", TAB_MARK)
    return _marked_format(_CONTROL_RE.sub(CONTROL_MARK, line))


def _buttons(buttons: list) -> list:
    options: list = []
    for button_id, label in buttons:
        options += ["--button", "%s=%s" % (button_id, sanitise(label, NAME_MAX))]
    return options


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


def hooks_reload() -> None:
    """Ask AGTerm to re-read its hooks file."""
    _run(["hooks", "reload"], timeout=_timeout(15))


def new_session(cwd: str, workspace_name: str, name: str, command: str, context: str) -> str:
    """Start a background session running `command`; returns its session id."""
    proc = _run(["session", "new"], [
        "--no-select", "--workspace-name", sanitise(workspace_name, NAME_MAX), "--create-workspace",
        "--cwd", cwd, "--name", sanitise(name, NAME_MAX), "--command", command, "--json"],
        timeout=_timeout(30))
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
        _run(["session", "context", sanitise(context, NAME_MAX)], ["--target", sid],
             timeout=_timeout(15))
    except AgtermError:
        try:
            close_session(sid)
        except AgtermError:
            pass
        raise
    return sid


def session_states() -> dict:
    """session id -> {status, status_changed_at, name}, across all open windows."""
    return session_snapshot()[0]


def session_snapshot() -> tuple:
    """(session states of all open windows, number of closed windows). A session that is not
    in the states may still be running in a closed window: with closed windows, absence is
    unknown, not gone."""
    windows = _result(_run(["window", "list"], ["--json"], timeout=_timeout(15))).get("windows") or []
    states: dict = {}
    closed = 0
    for win in windows:
        if not win.get("open", True):
            closed += 1
            continue
        tree = _result(_run(["tree"], ["--json", "--window", str(win["id"])], timeout=_timeout(15)))
        for ws in (tree.get("tree") or {}).get("workspaces") or []:
            for node in ws.get("sessions") or []:
                states[node["id"]] = {
                    "status": node.get("status"),
                    "status_changed_at": node.get("statusChangedAt"),
                    "name": node.get("name"),
                }
    return states, closed


def _call_timeout(timeout: Optional[float]) -> Optional[float]:
    return timeout if timeout is not None else _timeout(15)


def set_status(session_id: str, status: str, timeout: Optional[float] = None) -> None:
    """Set a session's agent status glyph (idle, active, completed, blocked)."""
    options = ["--target", session_id] + (["--blink"] if status == "blocked" else [])
    _run(["session", "status", status], options, timeout=_call_timeout(timeout))


def notify(session_id: str, title: str, body: str, timeout: Optional[float] = None) -> None:
    _run(["notify", sanitise(body, MESSAGE_MAX)],
         ["--title", sanitise(title, TITLE_MAX), "--target", session_id],
         timeout=_call_timeout(timeout))


def ask(session_id: str, title: str, message: str, buttons: list, timeout: int,
        default: Optional[str] = None) -> Optional[str]:
    """Ask the owner; returns the chosen button id, None on escape, cancel or timeout.
    `default` is the button highlighted at first (what a bare Enter picks)."""
    options = ["--message", sanitise(message, MESSAGE_MAX), "--target", session_id]
    if default:
        options += ["--default", default]
    options += _buttons(buttons)
    try:
        proc = _run(["ask", sanitise(title, TITLE_MAX)], options + ["--json"], timeout=timeout,
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


def ask_open(session_id: str, title: str, message: str, buttons: list,
             default: Optional[str] = None, timeout: Optional[float] = None) -> str:
    """Open a question without waiting; returns its dialog id. AGTerm refuses a second
    question on a session with an AgtermError whose text says "ask already pending"."""
    options = ["--message", sanitise(message, MESSAGE_MAX), "--target", session_id,
               "--no-block", "--json"]
    if default:
        options += ["--default", default]
    options += _buttons(buttons)
    result = _result(_run(["ask", "open", sanitise(title, TITLE_MAX)], options,
                          timeout=_call_timeout(timeout)))
    ask_id = result.get("id")
    if not ask_id:
        raise AgtermError("agtermctl did not return a dialog id")
    return str(ask_id)


def ask_result(ask_id: str, timeout: Optional[float] = None) -> tuple:
    """("pending", None) | ("answered", button id) | ("cancelled", None)."""
    proc = _run(["ask", "result", ask_id], ["--json"], timeout=_call_timeout(timeout),
                ok_codes=(0, 1, 2))
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        raise AgtermError("unreadable agtermctl output: %r" % proc.stdout[:200])
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        data = data["result"]
    if not isinstance(data, dict):
        raise AgtermError("unexpected agtermctl output")
    state = data.get("result")
    if state == "answered" and data.get("id"):
        return "answered", str(data["id"])
    if state == "pending":
        return "pending", None
    if data.get("ok") is False:
        raise AgtermError(str(data.get("error")))
    return "cancelled", None


def ask_cancel(ask_id: str, timeout: Optional[float] = None) -> None:
    """Close a question nobody needs any more; a dialog already closed is not an error."""
    _run(["ask", "cancel", ask_id], ["--json"], timeout=_call_timeout(timeout),
         ok_codes=(0, 1, 2))


def close_session(session_id: str) -> None:
    _run(["session", "close"], ["--target", session_id], timeout=_timeout(15))


def session_tail(session_id: str, lines: int) -> str:
    proc = _run(["session", "text"], ["--lines", str(lines), "--target", session_id], timeout=_timeout(15))
    return proc.stdout
