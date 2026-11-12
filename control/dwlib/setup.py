"""`dw setup`, `dw doctor` and the one-time import of the old project registry.

`setup` is the only code that edits the owner's Claude Code settings file and the terminal's
hooks file. It merges: one hook group in the settings, one marked block in the hooks file.
Everything else in both files is left exactly as it was, and each file is copied to a
timestamped backup before it is modified.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from . import agterm, autoapprove, guard, paths, runs, store

# The hook entry's own limit as Claude Code enforces it. The guard stops waiting well before
# this (guard.HOOK_MAX_WAIT_SECONDS); the larger value only keeps Claude Code from killing a
# guard that is legitimately waiting for the owner.
HOOK_TIMEOUT_SECONDS = 3600
MARK_START = "# >>> dodocs-workflow control"
MARK_END = "# <<< dodocs-workflow control"
BACKUP_INFIX = ".dw-backup-"
LEGACY_REGISTRY = "~/.claude/workspace/registry.json"


class SetupError(Exception):
    """A refusal that leaves every file untouched; the message is one line."""


def claude_settings_path() -> Path:
    override = os.environ.get("DW_CLAUDE_SETTINGS")
    return Path(override) if override else Path.home() / ".claude" / "settings.json"


def hooks_conf_path() -> Path:
    override = os.environ.get("DW_AGTERM_HOOKS_CONF")
    return Path(override) if override else Path.home() / ".config" / "agterm" / "hooks.conf"


def _quote(path: str) -> str:
    return "'" + path.replace("'", "'\\''") + "'"


def guard_command(dw_bin: str) -> str:
    return "%s guard" % _quote(dw_bin)


def hook_lines(dw_bin: str) -> list:
    return ["on status %s hook status" % _quote(dw_bin),
            "on session.closed %s hook session-closed" % _quote(dw_bin)]


def _block_lines(dw_bin: str) -> list:
    return [MARK_START] + hook_lines(dw_bin) + [MARK_END]


# -- file helpers --------------------------------------------------------------------------


def _backup(path: Path) -> Optional[str]:
    """Copy an existing file next to itself; returns the backup path (None: no file)."""
    if not path.exists():
        return None
    stamp = int(time.time())
    while True:
        dest = path.with_name("%s%s%d" % (path.name, BACKUP_INFIX, stamp))
        if not dest.exists():
            break
        stamp += 1
    shutil.copy2(str(path), str(dest))
    return str(dest)


def _write_text(path: Path, text: str) -> None:
    """Atomic replace. A symlinked file is written through, so the link itself survives."""
    target = Path(os.path.realpath(str(path)))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if target.exists():
            shutil.copymode(str(target), tmp)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, str(target))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read_text(path: Path) -> Optional[str]:
    try:
        with open(str(path), encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise SetupError("cannot read %s: %s" % (path, exc.__class__.__name__))


# -- the settings file ---------------------------------------------------------------------


def _load_settings(path: Path) -> tuple:
    """(data, text). A missing or empty file is an empty object; invalid JSON is a refusal."""
    text = _read_text(path)
    if text is None or not text.strip():
        return {}, text
    try:
        data = json.loads(text)
    except ValueError:
        raise SetupError("%s is not valid JSON; nothing was changed" % path)
    if not isinstance(data, dict):
        raise SetupError("%s is not a JSON object; nothing was changed" % path)
    return data, text


def _detect_style(text: Optional[str], data: dict) -> tuple:
    """(dump keyword arguments, trailing newline, exact). `exact` is False when re-dumping the
    untouched data would not reproduce the file byte for byte."""
    if not text or not text.strip():
        return {"indent": 2, "separators": (",", ": "), "ensure_ascii": False}, True, True
    newline = text.endswith("\n")
    body = text[:-1] if newline else text
    indent = None
    for line in body.splitlines()[1:]:
        stripped = line.lstrip(" \t")
        if stripped and stripped != line:
            lead = line[:len(line) - len(stripped)]
            indent = "\t" if lead[0] == "\t" else len(lead)
            break
    seps = [(",", ": "), (",", ":")] if indent is not None else [(", ", ": "), (",", ":")]
    for sep in seps:
        for ascii_only in (True, False):
            kwargs = {"indent": indent, "separators": sep, "ensure_ascii": ascii_only}
            if json.dumps(data, **kwargs) == body:
                return kwargs, newline, True
    return {"indent": indent, "separators": seps[0], "ensure_ascii": False}, newline, False


def _dump_settings(data: dict, text: Optional[str], original: dict) -> str:
    kwargs, newline, _ = _detect_style(text, original)
    return json.dumps(data, **kwargs) + ("\n" if newline else "")


def _is_guard_hook(hook) -> bool:
    """Whether one hook object is the guard entry, by the guard's own definition."""
    if not isinstance(hook, dict) or not isinstance(hook.get("command"), str):
        return False
    fd, tmp = tempfile.mkstemp(prefix="dw-hook-probe-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump({"hooks": {"PreToolUse": [{"hooks": [hook]}]}}, fh)
        return guard.guard_entry_present(Path(tmp))
    finally:
        os.unlink(tmp)


def _pre_tool_use(data: dict, create: bool):
    hooks = data.get("hooks")
    if hooks is None:
        if not create:
            return None
        hooks = data["hooks"] = {}
    if not isinstance(hooks, dict):
        raise SetupError("'hooks' in the Claude settings is not an object; nothing was changed")
    pre = hooks.get("PreToolUse")
    if pre is None:
        if not create:
            return None
        pre = hooks["PreToolUse"] = []
    if not isinstance(pre, list):
        raise SetupError("'hooks.PreToolUse' in the Claude settings is not a list; nothing was changed")
    return pre


def _guard_group(dw_bin: str) -> dict:
    return {"matcher": "*", "hooks": [
        {"type": "command", "command": guard_command(dw_bin), "timeout": HOOK_TIMEOUT_SECONDS}]}


def _settings_add_apply(path: Path, dw_bin: str) -> list:
    data, text = _load_settings(path)
    if guard.guard_entry_present(path):
        return []
    original = json.loads(json.dumps(data))
    _pre_tool_use(data, create=True).append(_guard_group(dw_bin))
    notes = []
    backup = _backup(path)
    if backup:
        notes.append("backup of %s saved to %s" % (path, backup))
    _write_text(path, _dump_settings(data, text, original))
    return notes


def _executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _stale_guard_hook(hook) -> bool:
    """Whether a hook object is a guard entry whose program is not an existing executable."""
    if not _is_guard_hook(hook):
        return False
    try:
        return not _executable(shlex.split(hook["command"])[0])
    except ValueError:
        return False


def _guard_hook_slots(data: dict) -> list:
    """(group, hook) for every guard hook in `hooks.PreToolUse`, whatever the group's matcher."""
    pre = _pre_tool_use(data, create=False) or []
    return [(g, h) for g in pre if isinstance(g, dict) and isinstance(g.get("hooks"), list)
            for h in g["hooks"] if _is_guard_hook(h)]


def _repair_guard_hooks(data: dict, dw_bin: str) -> list:
    """Leave exactly one guard entry, covering every tool and running an existing program:
    keep a healthy one if there is one, else point a covering one whose program is gone at
    `dw_bin`, else add a new group; every other guard hook is taken out of its group (a group
    left empty goes too). Other hooks and their groups are never changed. Changes `data` in
    place and returns preview lines; [] when there is nothing to repair or no guard hook."""
    slots = _guard_hook_slots(data)
    if not slots:
        return []
    keep = next((h for g, h in slots if guard.covers_all_tools(g) and not _stale_guard_hook(h)),
                None)
    lines: list = []
    if keep is None:
        keep = next((h for g, h in slots if guard.covers_all_tools(g)), None)
        if keep is not None:  # a covering entry whose program is gone: rewrite it in place
            lines += ["- " + keep["command"], "+ " + guard_command(dw_bin)]
            keep["command"] = guard_command(dw_bin)
    emptied = []
    for group, hook in slots:
        if hook is keep:
            continue
        lines.append("- %s (matcher %s)" % (hook["command"], json.dumps(group.get("matcher"))))
        group["hooks"][:] = [h for h in group["hooks"] if h is not hook]
        if not group["hooks"]:
            emptied.append(group)
    pre = _pre_tool_use(data, create=False)
    pre[:] = [g for g in pre if not any(g is e for e in emptied)]
    if keep is None:
        pre.append(_guard_group(dw_bin))
        lines.append("+ " + guard_command(dw_bin))
    return lines


def _settings_repair_apply(path: Path, dw_bin: str) -> list:
    """Apply `_repair_guard_hooks` to the settings file; nothing else changes."""
    data, text = _load_settings(path)
    original = json.loads(json.dumps(data))
    if not _repair_guard_hooks(data, dw_bin):
        return []
    notes = []
    backup = _backup(path)
    if backup:
        notes.append("backup of %s saved to %s" % (path, backup))
    _write_text(path, _dump_settings(data, text, original))
    return notes


def _settings_remove_apply(path: Path) -> list:
    data, text = _load_settings(path)
    original = json.loads(json.dumps(data))
    pre = _pre_tool_use(data, create=False)
    if not pre:
        return []
    kept, removed = [], False
    for group in pre:
        hooks = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(hooks, list):
            kept.append(group)
            continue
        rest = [h for h in hooks if not _is_guard_hook(h)]
        if len(rest) == len(hooks):
            kept.append(group)
            continue
        removed = True
        if rest:
            kept.append({**group, "hooks": rest})
    if not removed:
        return []
    if kept:
        data["hooks"]["PreToolUse"] = kept
    else:
        del data["hooks"]["PreToolUse"]
        if not data["hooks"]:
            del data["hooks"]
    notes = []
    backup = _backup(path)
    if backup:
        notes.append("backup of %s saved to %s" % (path, backup))
    _write_text(path, _dump_settings(data, text, original))
    return notes


def _preview(prefix: str, lines) -> list:
    return ["%s %s" % (prefix, line) for line in lines]


def _json_lines(value) -> list:
    return json.dumps(value, indent=2).splitlines()


def _style_warning(path: Path, text: Optional[str], data: dict) -> list:
    if text and text.strip() and not _detect_style(text, data)[2]:
        return ["! %s uses unusual JSON formatting; it will be rewritten in a regular style "
                "(the backup keeps the original)" % path]
    return []


# -- the terminal hooks file ---------------------------------------------------------------


def _find_block(lines: list, path: Path) -> Optional[tuple]:
    starts = [i for i, l in enumerate(lines) if l.strip() == MARK_START]
    ends = [i for i, l in enumerate(lines) if l.strip() == MARK_END]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise SetupError("%s has unbalanced dodocs-workflow markers; fix or remove them by hand, "
                         "nothing was changed" % path)
    return starts[0], ends[0]


def _conf_state(path: Path) -> tuple:
    """(text, lines with line endings, block span or None)."""
    text = _read_text(path) or ""
    lines = text.splitlines(keepends=True)
    return text, lines, _find_block(lines, path)


def _block_text(dw_bin: str, last_has_newline: bool = True) -> str:
    text = "\n".join(_block_lines(dw_bin)) + "\n"
    return text if last_has_newline else text[:-1]


def _conf_apply(path: Path, dw_bin: str) -> list:
    text, lines, span = _conf_state(path)
    if span is not None and [l.rstrip("\r\n") for l in lines[span[0] + 1:span[1]]] == hook_lines(dw_bin):
        return []
    if span is None:
        sep = "" if not text or text.endswith("\n") else "\n"
        new = text + sep + _block_text(dw_bin)
    else:
        tail_newline = lines[span[1]].endswith("\n")
        new = "".join(lines[:span[0]]) + _block_text(dw_bin, tail_newline) + "".join(lines[span[1] + 1:])
    notes = []
    backup = _backup(path)
    if backup:
        notes.append("backup of %s saved to %s" % (path, backup))
    _write_text(path, new)
    notes.append(_reload_hooks())
    return notes


def _conf_remove_apply(path: Path) -> list:
    text, lines, span = _conf_state(path)
    if span is None:
        return []
    notes = []
    backup = _backup(path)
    if backup:
        notes.append("backup of %s saved to %s" % (path, backup))
    _write_text(path, "".join(lines[:span[0]]) + "".join(lines[span[1] + 1:]))
    notes.append(_reload_hooks())
    return notes


def _reload_hooks() -> str:
    try:
        agterm.hooks_reload()
    except agterm.AgtermError:
        return "AGTerm did not respond; run `agtermctl hooks reload` when it is running"
    return "AGTerm hooks reloaded"


# -- plans ---------------------------------------------------------------------------------


def plan_setup(settings_path: Path, hooks_conf_path: Path, dw_bin: str) -> list:
    """Pending changes, each {"file", "description", "preview", "apply"}; [] when set up.

    Raises SetupError (and plans nothing) when a file cannot be merged safely.
    """
    settings_path, hooks_conf_path = Path(settings_path), Path(hooks_conf_path)
    items = []
    data, text = _load_settings(settings_path)
    _pre_tool_use(json.loads(json.dumps(data)), create=True)  # validates the shape
    if not _guard_hook_slots(json.loads(json.dumps(data))):
        group = _guard_group(dw_bin)
        items.append({
            "file": str(settings_path),
            "description": "add the approval guard to the Claude Code settings "
                           "(one PreToolUse hook; nothing else changes)",
            "preview": _style_warning(settings_path, text, data)
                       + _preview("+", _json_lines({"hooks": {"PreToolUse": ["...", group]}})),
            "apply": lambda: _settings_add_apply(settings_path, dw_bin),
        })
    else:
        repair = _repair_guard_hooks(json.loads(json.dumps(data)), dw_bin)
        if repair:
            items.append({
                "file": str(settings_path),
                "description": "replace the approval guard entry whose program is missing or "
                               "whose matcher does not cover all tools, leaving one entry "
                               "(nothing else changes)",
                "preview": _style_warning(settings_path, text, data) + repair,
                "apply": lambda: _settings_repair_apply(settings_path, dw_bin),
            })
    _, lines, span = _conf_state(hooks_conf_path)
    wanted = hook_lines(dw_bin)
    if span is None:
        items.append({
            "file": str(hooks_conf_path),
            "description": "add the status and session-closed hooks to the AGTerm hooks file",
            "preview": _preview("+", _block_lines(dw_bin)),
            "apply": lambda: _conf_apply(hooks_conf_path, dw_bin),
        })
    elif [l.rstrip("\r\n") for l in lines[span[0] + 1:span[1]]] != wanted:
        old = [l.rstrip("\r\n") for l in lines[span[0] + 1:span[1]]]
        items.append({
            "file": str(hooks_conf_path),
            "description": "update the dodocs-workflow block of the AGTerm hooks file",
            "preview": _preview("-", old) + _preview("+", wanted),
            "apply": lambda: _conf_apply(hooks_conf_path, dw_bin),
        })
    return items


def plan_remove(settings_path: Path, hooks_conf_path: Path) -> list:
    """Pending removals, same shape as `plan_setup`; [] when nothing of ours is installed."""
    settings_path, hooks_conf_path = Path(settings_path), Path(hooks_conf_path)
    items = []
    data, text = _load_settings(settings_path)
    pre = _pre_tool_use(data, create=False) or []
    gone = [h for g in pre if isinstance(g, dict) and isinstance(g.get("hooks"), list)
            for h in g["hooks"] if _is_guard_hook(h)]
    if gone:
        items.append({
            "file": str(settings_path),
            "description": "remove the approval guard from the Claude Code settings",
            "preview": _style_warning(settings_path, text, data) + _preview("-", _json_lines(gone)),
            "apply": lambda: _settings_remove_apply(settings_path),
        })
    _, lines, span = _conf_state(hooks_conf_path)
    if span is not None:
        items.append({
            "file": str(hooks_conf_path),
            "description": "remove the dodocs-workflow block from the AGTerm hooks file",
            "preview": _preview("-", [l.rstrip("\r\n") for l in lines[span[0]:span[1] + 1]]),
            "apply": lambda: _conf_remove_apply(hooks_conf_path),
        })
    return items


def remove_setup(settings_path: Path, hooks_conf_path: Path) -> list:
    """Remove exactly what `plan_setup` adds; returns the descriptions of what was removed."""
    done = []
    for item in plan_remove(settings_path, hooks_conf_path):
        item["apply"]()
        done.append(item["description"])
    return done


# -- doctor --------------------------------------------------------------------------------

OK, WARN, FAIL = "OK", "WARN", "FAIL"
_STATUS_LINE = re.compile(r"^on status (.+) hook status$")
_CLOSED_LINE = re.compile(r"^on session\.closed (.+) hook session-closed$")


def _single_path(text: str) -> Optional[str]:
    try:
        words = shlex.split(text)
    except ValueError:
        return None
    return words[0] if len(words) == 1 else None


def _settings_guard_paths(path: Path) -> list:
    try:
        data, _ = _load_settings(path)
    except SetupError:
        return []
    found = []
    pre = data.get("hooks", {}).get("PreToolUse") if isinstance(data.get("hooks"), dict) else None
    for group in pre if isinstance(pre, list) else []:
        for hook in group.get("hooks", []) if isinstance(group, dict) and isinstance(group.get("hooks"), list) else []:
            if _is_guard_hook(hook):
                try:
                    found.append(shlex.split(hook["command"])[0])
                except ValueError:
                    pass
    return found


def _check_hooks_conf(conf: Path) -> tuple:
    """(level, detail, dw paths mentioned)."""
    try:
        _, lines, span = _conf_state(conf)
    except SetupError as exc:
        return FAIL, str(exc), []
    if span is None:
        return FAIL, "no dodocs-workflow block in %s; run `dw setup`" % conf, []
    block = [l.rstrip("\r\n") for l in lines[span[0] + 1:span[1]]]
    status = [m for m in map(_STATUS_LINE.match, block) if m]
    closed = [m for m in map(_CLOSED_LINE.match, block) if m]
    missing = [name for name, found in (("status", status), ("session.closed", closed)) if not found]
    if missing:
        return FAIL, "missing the %s line in %s; run `dw setup`" % (" and ".join(missing), conf), []
    found = [_single_path(m.group(1)) for m in status + closed]
    return OK, "both lines present in %s" % conf, [p for p in found if p]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _check_tmux() -> Optional[tuple]:
    if not shutil.which(os.environ.get("DW_TMUX") or "tmux"):
        return None
    base = Path(os.environ.get("TMUX_TMPDIR") or "/tmp") / ("tmux-%d" % os.getuid())
    try:
        names = sorted(p.name for p in base.iterdir())
    except OSError:
        names = []
    stale = []
    for name in names:
        m = re.match(r"^claude-swarm-(\d+)$", name)
        if m and not _pid_alive(int(m.group(1))):
            stale.append(name)
    if not stale:
        return OK, "tmux", "no leftover claude-swarm servers"
    return WARN, "tmux", ("leftover servers whose owner process is gone (not touched): %s; "
                          "`tmux -L NAME kill-server` ends one" % ", ".join(stale))


def doctor_levels() -> list:
    """(check, OK|WARN|FAIL, detail) for every check. The only repair it makes: a `running` run
    whose AGTerm session is gone becomes `interrupted`."""
    settings, conf = claude_settings_path(), hooks_conf_path()
    results: list = []

    def add(check, level, detail):
        results.append((check, level, detail))

    records, corrupt = store.list_runs()  # before the sessions, so a run started now is not misjudged
    states = None
    closed = 0
    try:
        states, closed = agterm.session_snapshot()
        add("agtermctl", OK, "AGTerm reachable")
    except agterm.AgtermError as exc:
        add("agtermctl", FAIL, "AGTerm not reachable: %s" % (str(exc).splitlines() or ["error"])[0])

    if guard.guard_entry_present(settings):
        add("guard entry", OK, "installed in %s" % settings)
    elif guard.guard_entry_narrow(settings):
        add("guard entry", FAIL, "in %s does not cover all tools (its matcher leaves some out); "
                                 "run `dw setup`" % settings)
    else:
        add("guard entry", FAIL, "not installed in %s; run `dw setup`" % settings)

    level, detail, conf_paths = _check_hooks_conf(conf)
    add("hooks.conf", level, detail)

    dw_paths = _settings_guard_paths(settings) + conf_paths
    if dw_paths:
        bad = sorted({p for p in dw_paths if not _executable(p)})
        if bad:
            add("dw path", FAIL, "missing or not executable: %s; run `dw setup` again" % ", ".join(bad))
        else:
            add("dw path", OK, "%s" % ", ".join(sorted(set(dw_paths))))

    corrupt_files = [str(p) for p in corrupt]
    registry = None
    try:
        registry = store.load_registry()
    except store.CorruptFile as exc:
        corrupt_files.append(str(exc.path))
    try:
        _load_settings(settings)
    except SetupError:
        corrupt_files.append(str(settings))

    if registry is None:
        add("projects", FAIL, "registry unreadable")
    else:
        gone = ["%s (%s)" % (p.get("id"), p.get("path")) for p in registry.get("projects", [])
                if not os.path.isdir(str(p.get("path") or ""))]
        if gone:
            add("projects", FAIL, "path does not exist: %s" % ", ".join(gone))
        else:
            add("projects", OK, "%d project(s), all paths exist" % len(registry.get("projects", [])))
        problems, count = [], 0
        for p in registry.get("projects", []):
            good, bad = autoapprove.valid_entries(p)
            count += len(good)
            problems += bad
        if problems:
            add("auto-approve", WARN, "ignored by the guard: %s" % "; ".join(problems))
        elif count:
            add("auto-approve", OK, "%d automatic approval(s), all valid" % count)
        close_done = registry.get("close_done_sessions", True)
        if not isinstance(close_done, bool):
            add("close_done_sessions", WARN, "%r is not a boolean: sessions of done runs are "
                "kept open (use true or false)" % (close_done,))

    if states is None:
        add("runs", WARN, "skipped: AGTerm is not reachable")
    else:
        orphans = [r for r in records if r.get("state") == "running"
                   and r.get("agterm_session") and r["agterm_session"] not in states]
        if orphans and closed:
            add("runs", WARN, "%s not visible \u2014 a terminal window is closed; cannot tell"
                % ", ".join(r["id"] for r in orphans))
        else:
            marked = []
            for r in orphans:
                _, changed = runs.finish_run_changed(
                    r["id"], "interrupted", "AGTerm session is gone (found by dw doctor)")
                if changed:
                    marked.append(r["id"])
            if marked:
                add("runs", WARN, "marked interrupted, their terminal session is gone: %s"
                    % ", ".join(marked))
            else:
                add("runs", OK, "no running run has lost its terminal session")

    if corrupt_files:
        add("files", FAIL, "corrupt: %s" % ", ".join(corrupt_files))
    else:
        add("files", OK, "registry, run records and Claude settings are readable")

    try:
        data, _ = _load_settings(settings)
    except SetupError:
        data = None
    if data is not None:
        mode = data.get("teammateMode")
        if mode == "tmux":
            add("teammateMode", OK, "tmux")
        else:
            add("teammateMode", WARN, "is %s, not \"tmux\"; guard reach for in-process team members "
                                      "is unverified" % (json.dumps(mode) if mode is not None else "unset"))

    tmux = _check_tmux()
    if tmux:
        add(tmux[1], tmux[0], tmux[2])
    return results


def doctor() -> list:
    """(check, ok, detail) for every check; ok is False only for a failure (warnings are ok)."""
    return [(check, level != FAIL, detail) for check, level, detail in doctor_levels()]


# -- legacy import -------------------------------------------------------------------------


def import_legacy(legacy_path: Path, group_for: Callable[[dict], Optional[str]],
                  skipped: Optional[list] = None) -> list:
    """Add the projects of an old `registry.json`. The old file is only read.

    A project is skipped when `group_for` returns None or an empty string, when its path is not
    a directory, or when a project with the same id already exists; `skipped`, when given,
    receives (name, reason) for each.
    """
    skipped = skipped if skipped is not None else []
    try:
        with open(str(legacy_path), encoding="utf-8") as fh:
            legacy = json.load(fh)
    except FileNotFoundError:
        raise SetupError("no legacy registry at %s" % legacy_path)
    except (OSError, ValueError):
        raise SetupError("cannot read the legacy registry %s" % legacy_path)
    entries = legacy.get("projects") if isinstance(legacy, dict) else None
    if not isinstance(entries, list):
        raise SetupError("%s has no project list" % legacy_path)
    known = {p["id"] for p in store.load_registry().get("projects", [])}
    chosen = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        name = entry["name"]
        pid = store.slugify(name)
        path = entry.get("path")
        if not pid:
            skipped.append((name, "name has no letters or digits"))
        elif pid in known:
            skipped.append((name, "already registered as %s" % pid))
        elif not isinstance(path, str) or not os.path.isdir(path):
            skipped.append((name, "path does not exist: %s" % path))
        else:
            group = group_for(entry)
            if not group or not str(group).strip():
                skipped.append((name, "no group given"))
                continue
            known.add(pid)
            notes = entry.get("description")
            chosen.append({
                "id": pid, "name": name, "path": os.path.realpath(path), "group": str(group).strip(),
                "harness": "claude", "notes": notes if isinstance(notes, str) else "",
                "guard_rules": [],
            })
    added: list = []

    def merge(reg):
        present = {p["id"] for p in reg["projects"]}
        for project in chosen:
            if project["id"] in present:
                skipped.append((project["name"], "already registered as %s" % project["id"]))
                continue
            reg["projects"].append(project)
            added.append(project)
        return reg

    if chosen:
        store.update_json(paths.registry_path(), merge, store.default_registry())
    return added
