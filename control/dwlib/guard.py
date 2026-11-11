"""Approval guard: the `PreToolUse` hook that holds a run's risky actions for the owner.

`dw guard` reads the hook payload on stdin. Outside an active run it allows silently.
Inside one, an action that matches a rule is held: the run is marked blocked, the owner
is asked through AGTerm, and the answer allows or denies the tool call.

Classification rule for what the parser does not understand: a command whose program is
SENSITIVE (see `sensitive_programs`: every program a rule names, git, gh, ssh, scp, rsync,
curl, wget, osascript, dw, the shells, interpreters given inline code, and every wrapper this
module unwraps) is held as `control` ("command cannot be read") when anything that decides
its classification cannot be read: an unknown option shape of a wrapper or interpreter, a
word only known at run time (substitution, variable, glob, or brace too large to expand) in
the subcommand, remote, branch or refspec, URL, target path or HTTP-method position, or
quoting the lexer cannot follow. For any other program, unknown syntax is allowed. Control
checks (dw, the control point's files, agtermctl, other agent CLIs) always apply.

This catches direct and lightly wrapped risky commands from a cooperative agent. It is not
a sandbox: a script the agent writes and then runs is not read.
"""
from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from . import agterm, events, paths, runs, store

CATEGORIES = ("control", "destroy", "spend", "send", "deploy", "merge", "publish")
# Spike B: a hook may wait at least this long (entry timeout 3600 s; 900 s was the longest probe).
HOOK_MAX_WAIT_SECONDS = 900
ASK_TIMEOUT = min(HOOK_MAX_WAIT_SECONDS - 30, 3000)

PENDING_REASON = ("Approval is pending with the owner. Do not work around it. "
                  "Continue other work, then retry this exact action later.")
DENIED_REASON = "Denied by the owner. Do not attempt this action another way."
UNREADABLE = "command cannot be read"
DW_READ_ONLY = (["status"], ["queue"], ["tail"], ["project", "list"])
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
AGENT_HARNESSES = ("claude", "codex", "gemini", "aider", "opencode", "cursor-agent", "amp",
                   "goose", "crush", "qwen")
_RULE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class GuardError(Exception):
    pass


class NothingPending(Exception):
    pass


class ApprovalRefused(Exception):
    pass


# -- rules ----------------------------------------------------------------


def _default_rules_path() -> Path:
    installed = paths.home() / "guard-rules.default.json"
    if installed.is_file():
        return installed
    return Path(__file__).resolve().parent.parent / "guard-rules.json"


def _validate(rule) -> dict:
    if not isinstance(rule, dict) or not _RULE_ID_RE.match(str(rule.get("id") or "")) \
            or rule.get("category") not in CATEGORIES or not rule.get("describe"):
        raise GuardError("invalid guard rule: %r" % (rule,))
    return rule


def load_rules(project: dict) -> list:
    """Default rules plus the project's own `guard_rules`."""
    path = _default_rules_path()
    with open(str(path)) as fh:
        data = json.load(fh)
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        raise GuardError("no rules in %s" % path)
    extra = (project or {}).get("guard_rules") or []
    if not isinstance(extra, list):
        raise GuardError("guard_rules of project %s is not a list" % (project or {}).get("id"))
    return [_validate(r) for r in rules] + [_validate(r) for r in extra]


def run_context(run_id: str) -> dict:
    """A pseudo-rule naming the run a classification is for (its result note is writable)."""
    return {"run_id": run_id}


# -- paths ----------------------------------------------------------------


def _home() -> str:
    return os.path.expanduser("~")


def _expand(token: str) -> Optional[str]:
    """`token` with ~ and $HOME expanded; None when it depends on anything else at run time."""
    home = _home()
    text = token.replace("${HOME}", home).replace("$HOME", home)
    if "$" in text or "`" in text or "__dwsub" in text:
        return None
    if text == "~" or text.startswith("~/"):
        text = home + text[1:]
    elif text.startswith("~"):
        text = os.path.expanduser(text)
    return text


def _resolve(token: str, cwd: Optional[str]) -> Optional[str]:
    text = _expand(token)
    if text is None or "\n" in text or "\0" in text or len(text) > 4096:
        return None
    if not os.path.isabs(text):
        if cwd is None:
            return None
        text = os.path.join(cwd, text)
    return os.path.realpath(text)


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def settings_path() -> Path:
    override = os.environ.get("DW_CLAUDE_SETTINGS")
    return Path(override) if override else Path(_home()) / ".claude" / "settings.json"


GLOB_MAX_ENTRIES = 5000
GLOB_MAX_SECONDS = 0.5


def _bounded_glob(pattern: str) -> tuple:
    """(matching paths, complete). Bash-style: a component not starting with "." does not
    match dot files. Stops after GLOB_MAX_ENTRIES directory entries or GLOB_MAX_SECONDS."""
    started = time.monotonic()
    parts = [p for p in pattern.split("/") if p]
    current = ["/"] if pattern.startswith("/") else ["."]
    listed = 0
    for part in parts:
        if not glob.has_magic(part):
            current = [os.path.join(c, part) for c in current]
            continue
        found = []
        for base in current:
            try:
                entries = os.scandir(base)
            except OSError:
                continue
            with entries:
                for entry in entries:
                    listed += 1
                    if listed > GLOB_MAX_ENTRIES or time.monotonic() - started > GLOB_MAX_SECONDS:
                        return found, False
                    if entry.name.startswith(".") and not part.startswith("."):
                        continue
                    if fnmatch.fnmatchcase(entry.name, part):
                        found.append(os.path.join(base, entry.name))
        current = found
        if not current:
            break
    return [c for c in current if os.path.lexists(c)], True


class _Protected:
    """The control point's own files, as real paths."""

    def __init__(self, run_id: Optional[str]):
        home = _home()
        self.dirs = sorted({os.path.realpath(str(paths.home())),
                            os.path.realpath(os.path.join(home, ".dodocs-workflow"))})
        self.files = {os.path.realpath(os.path.join(home, ".claude", "settings.json")),
                      os.path.realpath(str(settings_path())),
                      os.path.realpath(os.path.join(home, ".config", "agterm", "hooks.conf"))}
        self.home = os.path.realpath(home)
        self.note = os.path.realpath(str(paths.result_note_path(run_id))) if run_id else None
        self.markers = [".dodocs-workflow", "agterm/hooks.conf"] + self.dirs + sorted(self.files)

    def hit(self, path: str) -> bool:
        if path == self.note:
            return False
        if any(_inside(path, d) for d in self.dirs) or path in self.files:
            return True
        if os.path.basename(path) in ("settings.json", "settings.local.json") \
                and os.path.basename(os.path.dirname(path)) == ".claude":
            return True  # any Claude settings file can switch hooks off
        if path not in ("/", self.home) and not _inside(self.home, path):
            return any(_inside(t, path) for t in list(self.files) + self.dirs)
        return False

    def pattern_hit(self, text: str, cwd: Optional[str]) -> bool:
        """For a path with glob characters, braces or run-time parts: may it name a protected path?"""
        home = _home()
        text = text.replace("${HOME}", home).replace("$HOME", home)
        if text == "~" or text.startswith("~/"):
            text = home + text[1:]
        cuts = [text.find(ch) for ch in ("*", "?", "[", "{", "$", "`", "__dwsub") if ch in text]
        if not cuts:
            resolved = _resolve(text, cwd)
            return resolved is not None and self.hit(resolved)
        cut = min(cuts)
        dynamic = any(ch in text for ch in ("$", "`", "__dwsub")) or "{" in text
        prefix = text[:cut]
        if not os.path.isabs(prefix):
            if cwd is None:
                return False
            prefix = os.path.join(cwd, prefix)
        head, base = os.path.split(prefix)
        rdir = os.path.realpath(head or "/")
        rprefix = rdir.rstrip("/") + "/" + base
        targets = self.dirs + sorted(self.files)
        if any(_inside(rdir, d) for d in self.dirs):
            return True
        if base and any(t.startswith(rprefix) for t in targets):
            return True
        def undecided() -> bool:  # fail closed next to the control point's own files
            claude = os.path.realpath(os.path.join(home, ".claude"))
            if _inside(rdir, claude):
                return True
            for d in self.dirs:
                parent, name = os.path.split(d)
                if rdir == parent and name.startswith(base):
                    return True
            return False

        if dynamic:
            return undecided()
        pattern = text if os.path.isabs(text) else os.path.join(cwd or "/", text)
        try:
            found, complete = _bounded_glob(pattern)
        except (re.error, ValueError):
            return undecided()
        if not complete:
            return True  # too much to look at: cannot decide, so hold
        return any(self.hit(os.path.realpath(f)) for f in found)

    def text_hit(self, text: str) -> bool:
        clean = text.replace("\\", "")
        return any(m in clean for m in self.markers) or \
            bool(re.search(r"\.claude/settings(\.local)?\.json", clean))

    def token_hit(self, token: str, cwd: Optional[str]) -> bool:
        candidates = [token]
        if "=" in token:
            candidates.append(token.split("=", 1)[1])
        for cand in candidates:
            if not cand or len(cand) > 4096:
                continue
            plain = cand.replace("${HOME}", "").replace("$HOME", "")
            if any(ch in plain for ch in "*?[{") or _expand(cand) is None:
                if cand not in ("[", "[[", "{", "}") and self.pattern_hit(cand, cwd):
                    return True
                continue
            resolved = _resolve(cand, cwd)
            if resolved is not None:
                if resolved == self.note:
                    return False
                if self.hit(resolved):
                    return True
        text = token.replace("\\", "")
        if any(m in text for m in self.markers) or \
                re.search(r"\.claude/settings(\.local)?\.json", text):
            return True
        return False


# -- shell lexing ----------------------------------------------------------


class _Unreadable(Exception):
    pass


def _new_segment(pipe_in: bool) -> dict:
    return {"words": [], "redirects": [], "heredocs": [], "pipe_in": pipe_in,
            "pipe_out": False, "keep": False}


class _Lexer:
    """Splits a shell command into simple-command segments.

    Command and process substitutions are cut out (their bodies are classified as commands
    of their own) and replaced by placeholder words. Redirections and here-documents are
    taken out of the words. Anything this lexer cannot follow raises _Unreadable.
    """

    def __init__(self, text: str):
        self.s = text
        self.i = 0
        self.n = len(text)
        self.segments: list = []
        self.subs: list = []
        self.seg = _new_segment(False)
        self.pending: list = []

    def run(self) -> "_Lexer":
        s = self.s
        while self.i < self.n:
            c = s[self.i]
            nxt = s[self.i + 1:self.i + 2]
            if c in " \t\r":
                self.i += 1
            elif c == "\\" and nxt == "\n":
                self.i += 2
            elif c == "\n":
                self.end()
                self.i += 1
                self.heredoc_bodies()
            elif c == ";":
                self.end()
                self.i += 1
            elif c == "&" and nxt == "&":
                self.end()
                self.i += 2
            elif c == "&" and nxt == ">":
                self.redirect()
            elif c == "&":
                self.end()
                self.i += 1
            elif c == "|":
                if nxt == "|":
                    self.end()
                    self.i += 2
                else:
                    self.end(pipe=True)
                    self.i += 2 if nxt == "&" else 1
            elif c in "<>" and nxt == "(":
                self.seg["words"].append(self.substitution(self.i + 2))
            elif c in "()":
                self.end()
                self.i += 1
            elif c == "#":
                while self.i < self.n and s[self.i] != "\n":
                    self.i += 1
            elif c in "<>" or re.match(r"\d+[<>]", s[self.i:self.i + 12]):
                self.redirect()
            else:
                self.seg["words"].append(self.read_word())
        self.end()
        if self.pending:
            for _delim, _strip, seg in self.pending:
                seg["heredocs"].append("")
        return self

    def end(self, pipe: bool = False) -> None:
        seg = self.seg
        seg["pipe_out"] = pipe
        if seg["words"] or seg["redirects"] or seg["heredocs"] or seg["keep"]:
            self.segments.append(seg)
        self.seg = _new_segment(pipe)

    def heredoc_bodies(self) -> None:
        for delim, strip, seg in self.pending:
            lines = []
            while self.i < self.n:
                j = self.s.find("\n", self.i)
                line = self.s[self.i:] if j < 0 else self.s[self.i:j]
                self.i = self.n if j < 0 else j + 1
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                lines.append(line)
            seg["heredocs"].append("\n".join(lines))
        self.pending = []

    def redirect(self) -> None:
        m = re.match(r"(\d*|&)(>>|>&|>\||<<<|<<-|<<|<&|<>|>|<)", self.s[self.i:])
        if not m:
            raise _Unreadable("redirection")
        op = m.group(2)
        self.i += m.end()
        while self.i < self.n and self.s[self.i] in " \t":
            self.i += 1
        word = self.read_word()
        if not word:
            raise _Unreadable("redirection without a target")
        if op in ("<<", "<<-"):
            try:
                delim = "".join(shlex.split(word))
            except ValueError:
                raise _Unreadable("here-document delimiter")
            self.seg["keep"] = True
            self.pending.append((delim, op == "<<-", self.seg))
        elif op == "<<<":
            self.seg["heredocs"].append(_unquote(word))
        elif op in (">&", "<&") and re.fullmatch(r"\d+-?|-", word):
            return
        else:
            self.seg["redirects"].append(word)

    def read_word(self) -> str:
        s = self.s
        out: list = []
        while self.i < self.n:
            c = s[self.i]
            nxt = s[self.i + 1:self.i + 2]
            if c in " \t\r\n;&|()<>":
                break
            if c == "\\":
                if nxt == "\n":
                    self.i += 2
                    continue
                out.append(s[self.i:self.i + 2])
                self.i += 2
            elif c == "'":
                j = s.find("'", self.i + 1)
                if j < 0:
                    raise _Unreadable("unterminated quote")
                out.append(s[self.i:j + 1])
                self.i = j + 1
            elif c == '"':
                out.append(self.read_double())
            elif c == "$" and nxt == "'":
                out.append(self.ansi_c())
            elif c == "$" and s.startswith("$((", self.i):
                j = self.close_paren(self.i + 3, 2)
                out.append(s[self.i:j + 1])
                self.i = j + 1
            elif c == "$" and nxt == "(":
                out.append(self.substitution(self.i + 2))
            elif c == "$" and nxt == "{":
                j = self.close_brace(self.i + 2)
                out.append(s[self.i:j + 1])
                self.i = j + 1
            elif c == "`":
                out.append(self.backtick())
            else:
                out.append(c)
                self.i += 1
        return "".join(out)

    def read_double(self) -> str:
        s = self.s
        out = ['"']
        self.i += 1
        while self.i < self.n:
            c = s[self.i]
            nxt = s[self.i + 1:self.i + 2]
            if c == "\\":
                out.append(s[self.i:self.i + 2])
                self.i += 2
            elif c == '"':
                out.append(c)
                self.i += 1
                return "".join(out)
            elif c == "$" and s.startswith("$((", self.i):
                j = self.close_paren(self.i + 3, 2)
                out.append(s[self.i:j + 1])
                self.i = j + 1
            elif c == "$" and nxt == "(":
                out.append(self.substitution(self.i + 2))
            elif c == "`":
                out.append(self.backtick())
            else:
                out.append(c)
                self.i += 1
        raise _Unreadable("unterminated quote")

    def ansi_c(self) -> str:
        s = self.s
        j = self.i + 2
        while j < self.n and s[j] != "'":
            j += 2 if s[j] == "\\" else 1
        if j >= self.n:
            raise _Unreadable("unterminated quote")
        raw = s[self.i + 2:j]
        self.i = j + 1
        try:
            decoded = raw.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except (UnicodeError, ValueError):
            raise _Unreadable("ANSI-C quote")
        return shlex.quote(decoded)

    def close_paren(self, start: int, depth: int = 1) -> int:
        """Index of the `)` closing a group opened before `start`, respecting quotes."""
        s = self.s
        j = start
        heredocs: list = []
        while j < self.n:
            c = s[j]
            if c == "\\":
                j += 2
                continue
            if c == "\n" and heredocs:
                j += 1
                for delim, strip in heredocs:
                    while j < self.n:
                        k = s.find("\n", j)
                        line = s[j:] if k < 0 else s[j:k]
                        j = self.n if k < 0 else k + 1
                        if (line.lstrip("\t") if strip else line) == delim:
                            break
                heredocs = []
                continue
            if c == "<" and s.startswith("<<", j) and not s.startswith("<<<", j):
                m = re.match(r"<<(-?)[ \t]*(['\"]?)([A-Za-z0-9_.-]+)\2", s[j:])
                if m:
                    heredocs.append((m.group(3), m.group(1) == "-"))
                    j += m.end()
                    continue
            if c == "'":
                k = s.find("'", j + 1)
                if k < 0:
                    raise _Unreadable("unterminated quote")
                j = k + 1
                continue
            if c == '"':
                j = self.close_double(j + 1) + 1
                continue
            if c == "`":
                k = s.find("`", j + 1)
                if k < 0:
                    raise _Unreadable("unterminated backtick")
                j = k + 1
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        raise _Unreadable("unterminated substitution")

    def close_double(self, start: int) -> int:
        s = self.s
        j = start
        while j < self.n:
            c = s[j]
            if c == "\\":
                j += 2
                continue
            if c == '"':
                return j
            if c == "$" and s[j + 1:j + 2] == "(":
                j = self.close_paren(j + 2) + 1
                continue
            j += 1
        raise _Unreadable("unterminated quote")

    def close_brace(self, start: int) -> int:
        depth = 1
        j = start
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        raise _Unreadable("unterminated parameter expansion")

    def placeholder(self, body: str) -> str:
        self.subs.append(body)
        return "__dwsub%d__" % (len(self.subs) - 1)

    def substitution(self, start: int) -> str:
        j = self.close_paren(start)
        body = self.s[start:j]
        self.i = j + 1
        return self.placeholder(body)

    def backtick(self) -> str:
        s = self.s
        j = self.i + 1
        while j < self.n and s[j] != "`":
            j += 2 if s[j] == "\\" else 1
        if j >= self.n:
            raise _Unreadable("unterminated backtick")
        body = s[self.i + 1:j].replace("\\`", "`")
        self.i = j + 1
        return self.placeholder(body)


def _unquote(word: str) -> str:
    try:
        parts = shlex.split(word)
    except ValueError:
        raise _Unreadable("quoting")
    return " ".join(parts) if parts else ""


BRACE_LIMIT = 64
_SEQ_RE = re.compile(r"^(-?\d+|[A-Za-z])\.\.(-?\d+|[A-Za-z])(\.\.-?\d+)?$")


class _TooMany(Exception):
    pass


def _brace_alternatives(inner: str) -> Optional[list]:
    """Alternatives of an unquoted brace body: a,b,c or a sequence x..y; None if neither."""
    parts, depth, quote, start, j = [], 0, None, 0, 0
    while j < len(inner):
        c = inner[j]
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"':
                j += 1
        elif c in "'\"":
            quote = c
        elif c == "\\":
            j += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(inner[start:j])
            start = j + 1
        j += 1
    if parts:
        return parts + [inner[start:]]
    m = _SEQ_RE.match(inner)
    if not m:
        return None
    a, b = m.group(1), m.group(2)
    step = abs(int(m.group(3)[2:])) if m.group(3) else 1
    step = step or 1
    if a.lstrip("-").isdigit() and b.lstrip("-").isdigit():
        lo, hi = int(a), int(b)
        if abs(hi - lo) // step + 1 > BRACE_LIMIT:
            raise _TooMany()
        values = [str(v) for v in (range(lo, hi + 1, step) if lo <= hi else range(lo, hi - 1, -step))]
    elif a.isalpha() and b.isalpha():
        lo, hi = ord(a), ord(b)
        if abs(hi - lo) // step + 1 > BRACE_LIMIT:
            raise _TooMany()
        values = [chr(v) for v in (range(lo, hi + 1, step) if lo <= hi else range(lo, hi - 1, -step))]
    else:
        return None
    if len(values) > BRACE_LIMIT:
        raise _TooMany()
    return values


def _brace_expand(word: str) -> list:
    """Bash brace expansion of one raw word (quotes kept). Raises _TooMany past the bound."""
    quote = None
    j = 0
    while j < len(word):
        c = word[j]
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"':
                j += 1
        elif c in "'\"":
            quote = c
        elif c == "\\":
            j += 1
        elif c == "{" and (j == 0 or word[j - 1] != "$"):
            depth, k, q = 1, j + 1, None
            while k < len(word) and depth:
                ch = word[k]
                if q:
                    if ch == q:
                        q = None
                elif ch in "'\"":
                    q = ch
                elif ch == "\\":
                    k += 1
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                k += 1
            if depth == 0:
                alternatives = _brace_alternatives(word[j + 1:k - 1])
                if alternatives is not None:
                    out: list = []
                    for alt in alternatives:
                        out += _brace_expand(word[:j] + alt + word[k:])
                        if len(out) > BRACE_LIMIT:
                            raise _TooMany()
                    return out
        j += 1
    return [word]


def _tokens(words: list) -> list:
    out = []
    for w in words:
        try:
            expanded = _brace_expand(w) if "{" in w else [w]
        except _TooMany:
            expanded = [w]  # left unexpanded: the braces make it dynamic, like a glob
        for one in expanded:
            try:
                parts = shlex.split(one)
            except ValueError:
                raise _Unreadable("quoting")
            if parts:  # an unquoted empty expansion is no word at all
                out.append(" ".join(parts))
    return out


# -- shell analysis ----------------------------------------------------------

SHELLS = ("sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh")
_INTERPRETER_RE = re.compile(r"^(python[0-9.]*|pypy[0-9.]*|perl[0-9.]*|ruby[0-9.]*|node|nodejs|php[0-9.]*|"
                             r"deno|bun|lua[0-9.]*|luajit|Rscript|julia|tclsh|wish|pwsh|powershell|"
                             r"groovy|elixir|erl|escript|swift|expect)$")
_KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!", "{", "}",
             "coproc"}
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
SQL_CLIENTS = {"psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "clickhouse-client", "clickhouse",
               "cockroach", "mongosh", "mongo", "redis-cli", "duckdb", "pgcli", "mycli", "usql",
               "litecli"}
_SQL_DESTRUCTIVE_RE = re.compile(
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|USER|ROLE|COLLECTION|OWNED)\b"
    r"|\bTRUNCATE\b|\bDELETE\s+FROM\b(?![^;]*\bWHERE\b)|\bALTER\s+TABLE\b[^;]*\bDROP\b"
    r"|\bFLUSH(ALL|DB)\b|dropDatabase\s*\(|\.drop\s*\(|\bdeleteMany\s*\(\s*\{\s*\}\s*\)",
    re.I)
_LOCAL_HOSTS = ("localhost", "0.0.0.0", "::1", "host.docker.internal")


class _Ctx:
    def __init__(self, cwd, project_path, rules, run_id, full_text=""):
        self.cwd = os.path.realpath(cwd) if cwd else None
        self.project = os.path.realpath(project_path) if project_path else None
        self.rules = rules
        self.protected = _Protected(run_id)
        self.full_text = full_text
        self.incomplete = False
        self.git_cache: dict = {}
        self.budget = {"left": ANALYSIS_BUDGET}  # shared by every fork of this context
        self._plausible: Optional[set] = None

    def fork(self) -> "_Ctx":
        other = _Ctx.__new__(_Ctx)
        other.__dict__.update(self.__dict__)
        other.incomplete = False
        return other


_UNREADABLE_RULE = {"id": "control-unreadable", "category": "control", "describe": UNREADABLE,
                    "tool": "Bash"}


def _unreadable_match() -> dict:
    return {"id": "control-unreadable", "category": "control", "describe": UNREADABLE}


def _dynamic(token: str) -> bool:
    if token in ("[", "[[", "{", "}", "{}"):
        return False
    return _expand(token) is None or any(ch in token for ch in "*?[{")


def _flags_values(tokens, value_flags):
    """Positional arguments, skipping options and the values of options that take one."""
    out = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            out.extend(tokens[i + 1:])
            break
        if t.startswith("-") and len(t) > 1:
            if t in value_flags:
                i += 2
                continue
            if not t.startswith("--") and len(t) > 2:
                for k, ch in enumerate(t[1:], 1):
                    if "-" + ch in value_flags:
                        if k == len(t) - 1:
                            i += 1
                        break
            i += 1
            continue
        out.append(t)
        i += 1
    return out


def _strip_prefix(tokens: list) -> list:
    while tokens:
        t = tokens[0]
        if t in ("for", "case", "select"):
            return []
        if t in _KEYWORDS or t.endswith("()"):
            tokens = tokens[1:]
        elif t == "function":
            tokens = tokens[2:]
        elif _ASSIGNMENT_RE.match(t):
            tokens = tokens[1:]
        else:
            break
    return tokens


def _skip_options(tokens: list, start: int, value_opts=(), stop_at_positional=True) -> int:
    i = start
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            return i + 1
        if t in value_opts:
            i += 2
        elif t.startswith("-") and len(t) > 1:
            i += 1
        elif _ASSIGNMENT_RE.match(t):
            i += 1
        else:
            break
    return i


# Wrappers run another command given in their arguments. Their options are not parsed:
# every suffix of the arguments is classified as a command, and so is every argument that
# holds a command string (see _command_strings).
WRAPPERS = {"env", "sudo", "doas", "command", "builtin", "nohup", "chronic", "unbuffer", "time",
            "exec", "nice", "ionice", "caffeinate", "stdbuf", "watch", "dotenv", "timeout",
            "gtimeout", "xargs", "npx", "bunx", "pnpx", "flock", "setsid", "chroot", "script",
            "parallel", "taskset", "cgexec", "systemd-run", "runuser", "su", "nsenter", "unshare",
            "firejail", "proxychains", "proxychains4", "tsocks", "torsocks", "strace", "ltrace",
            "dtruss", "valgrind", "entr", "nodemon"}
_RUNNERS = {"pnpm": ("dlx", "exec"), "yarn": ("dlx", "exec"), "npm": ("exec", "x"),
            "uv": ("run", "tool"), "uvx": (), "poetry": ("run",), "pipenv": ("run",),
            "bundle": ("exec",), "op": ("run",), "rye": ("run",), "pdm": ("run",),
            "hatch": ("run",), "pipx": ("run",)}
_REMOTE_PARALLEL = re.compile(r"^(-S.*|--sshlogin(=.*)?|--sshloginfile(=.*)?|--slf(=.*)?)$")
MAX_WRAPPER_TOKENS = 200
ANALYSIS_BUDGET = 400  # command analyses per tool call; past it the command is unreadable
MAX_DEPTH = 12
# Programs that read their commands from standard input, or start a shell, when no command
# is given in their arguments.
_SHELL_STARTERS = {"su", "runuser", "nsenter", "unshare", "firejail", "chroot", "sudo", "doas"}


def _command_strings(token: str) -> list:
    """Parts of one argument that may be a command given as a string: the argument, the part
    after its first "=", and an attached short option's value (-c'cmd', -qccmd)."""
    out = [token]
    if "=" in token:
        out.append(token.split("=", 1)[1])
    if token.startswith("-") and not token.startswith("--"):
        out += [token[k:] for k in range(2, min(len(token), 6))]
    return [c for c in out if re.search(r"\s", c)]


def _plausible_word(word: str, ctx: _Ctx) -> bool:
    if word not in ("[", "[[", "{", "}") and _dynamic(word):
        return True
    if ctx._plausible is None:
        ctx._plausible = sensitive_programs(ctx.rules) | set(AGENT_HARNESSES) | {"agtermctl"}
    name = os.path.basename(word)
    return name in ctx._plausible or bool(_INTERPRETER_RE.match(name))


def _plausible_command(text: str, ctx: _Ctx) -> bool:
    """Whether a string may be a command worth classifying: some simple command in it starts
    with a sensitive program, a wrapper, a shell or an interpreter (or a computed word)."""
    try:
        lexed = _Lexer(text).run()
    except _Unreadable:
        words = text.split()
        return bool(words) and _plausible_word(words[0], ctx)
    if lexed.subs:
        return True
    for seg in lexed.segments:
        try:
            words = _strip_prefix(_tokens(seg["words"]))
        except _Unreadable:
            return True
        if words and _plausible_word(words[0], ctx):
            return True
    return False


def _string_matches(texts: list, ctx: _Ctx, depth: int) -> list:
    """Classify each plausible command string in full, unreadable results included."""
    out: list = []
    for text in texts:
        if _plausible_command(text, ctx):
            out += _shell_matches(text, ctx.fork(), depth + 1)
    return out


def _has_command_string(tokens: list) -> bool:
    return any(t in ("-c", "--command") or t.startswith("--command=") or
               (t.startswith("-") and not t.startswith("--") and "c" in t[1:]) for t in tokens)


def _starts_shell_without_command(name: str, tokens: list) -> bool:
    """For a program that may start a shell: is no command given in its arguments?"""
    args = tokens[1:]
    if name in ("su",):
        return not _has_command_string(args)
    if name == "runuser":
        if _has_command_string(args):
            return False
        return not ("-u" in args and len(args) > args.index("-u") + 2)
    if name in ("sudo", "doas"):
        for i, t in enumerate(args):
            if t in ("--shell", "--login") or (t.startswith("-") and not t.startswith("--")
                                               and any(c in t[1:] for c in "si")):
                return not any(not a.startswith("-") for a in args[i + 1:])
        return False
    operands = [t for t in args if not t.startswith("-")]
    return len(operands) <= (1 if name == "chroot" else 0)


def _wrapper_matches(tokens: list, seg: dict, ctx: _Ctx, depth: int, start: int = 1) -> list:
    """Classify a wrapper call without parsing its options."""
    name = os.path.basename(tokens[0])
    if len(tokens) > MAX_WRAPPER_TOKENS or depth > MAX_DEPTH:
        return [_unreadable_match()]
    if name == "command" and tokens[1:2] in (["-v"], ["-V"]):
        return []
    out: list = []
    if name == "parallel":
        if any(_REMOTE_PARALLEL.match(t) for t in tokens[1:]):
            return [{"id": "remote-execution", "category": "deploy",
                     "describe": "run commands on remote hosts: %s" % _short(" ".join(tokens))}]
        if all(t.startswith("-") or t.startswith(":::") for t in tokens[1:]):
            return [_unreadable_match()]  # the commands come from standard input
    if name in _SHELL_STARTERS:
        for body in seg["heredocs"]:
            out += _shell_matches(body, ctx.fork(), depth + 1)
        if seg["pipe_in"] and not seg["heredocs"]:
            out.append(_unreadable_match())  # its input comes from another command
        elif not seg["heredocs"] and _starts_shell_without_command(name, tokens):
            out.append(_unreadable_match())  # an interactive shell this guard cannot see
    sub = ctx.fork()
    if name in ("env", "sudo", "doas", "su", "runuser", "nsenter", "chroot", "unshare") and \
            any(t in ("-C", "-D", "--chdir", "-w", "--wd") or t.startswith("--chdir=") or
                (t.startswith("-C") and len(t) > 2) for t in tokens):
        sub.cwd = None  # moved somewhere this guard does not follow
    incomplete = name in ("xargs", "parallel")
    inner_seg = dict(seg, heredocs=[] if name in _SHELL_STARTERS else seg["heredocs"])
    for k in range(start, len(tokens)):
        if tokens[k].startswith("-") or re.search(r"\s", tokens[k]):
            continue  # an option or a command string (read below) is not a program name
        out += _analyze(tokens[k:], [], inner_seg, sub.fork(), depth + 1, incomplete)
    for token in tokens[start:]:
        out += _string_matches(_command_strings(token), sub, depth)
    return out


def _shell_matches(text: str, ctx: _Ctx, depth: int = 0) -> list:
    if depth > 6:
        return [_unreadable_match()]
    try:
        lexed = _Lexer(text).run()
    except _Unreadable:
        return [_unreadable_match()]
    matches: list = []
    start = ctx.fork()
    for seg in lexed.segments:
        matches += _segment_matches(seg, ctx, depth)
    for body in lexed.subs:
        matches += _shell_matches(body, start.fork(), depth + 1)
    return matches


def _segment_matches(seg: dict, ctx: _Ctx, depth: int) -> list:
    try:
        original = _tokens(seg["words"])
        redirects = [_unquote(w) for w in seg["redirects"]]
    except _Unreadable:
        return [_unreadable_match()]
    return _analyze(original, redirects, seg, ctx, depth)


# Interpreter switches: (inline-code letters, plain flag letters, letters taking a value
# (attached, or the next token), letters whose value may only be attached).
_GIT_ENV_RE = re.compile(
    r"^(GIT_CONFIG(_GLOBAL|_SYSTEM|_COUNT|_PARAMETERS|_NOSYSTEM|_KEY_\w+|_VALUE_\w+)?|GIT_DIR|"
    r"GIT_WORK_TREE|GIT_COMMON_DIR|GIT_SSH|GIT_SSH_COMMAND|GIT_SSH_VARIANT|GIT_EXEC_PATH|"
    r"GIT_ALTERNATE_OBJECT_DIRECTORIES|GIT_NAMESPACE|GIT_PROXY_COMMAND|GIT_ASKPASS)=")
_EXACT_VARIABLE_RE = re.compile(r"\s*\$\{?\w+\}?\s*")


def _run_time_text(token: str) -> bool:
    """An argument whose whole text is only known at run time."""
    return "__dwsub" in token or bool(_EXACT_VARIABLE_RE.fullmatch(token))


def _analyze(original: list, redirects: list, seg: dict, ctx: _Ctx, depth: int,
             incomplete: bool = False) -> list:
    """Matches for one simple command, given as tokens."""
    ctx.budget["left"] -= 1
    if ctx.budget["left"] < 0 or depth > MAX_DEPTH:
        return [_unreadable_match()]
    ctx.incomplete = incomplete
    matches: list = []
    tokens = original
    if any(_GIT_ENV_RE.match(t) for t in original):
        matches.append(_unreadable_match())
    for _ in range(16):
        tokens = _strip_prefix(tokens)
        if not tokens:
            break
        prog = tokens[0]
        if _dynamic(prog):
            matches.append(_unreadable_match())
            tokens = []
            break
        name = os.path.basename(prog)
        if name in SHELLS:
            # Every argument may be the script (-c, -lc, an attached -c'...'): classify each
            # as a command. Arguments only known at run time cannot be read.
            args = tokens[1:]
            for arg in args:
                if _run_time_text(arg):
                    matches.append(_unreadable_match())
                    continue
                matches += _string_matches([arg] + _command_strings(arg)[1:], ctx, depth)
            operands = [a for a in args if not a.startswith(("-", "+"))]
            stdin_program = not operands or operands[0] in ("-", "/dev/stdin") or "-s" in args
            if stdin_program and seg["pipe_in"]:
                matches.append(_unreadable_match())
            for body in seg["heredocs"]:
                matches += _shell_matches(body, ctx.fork(), depth + 1)
            tokens = []
            break
        if _INTERPRETER_RE.match(name):
            # Options are not parsed: every argument and any here-document is scanned as code.
            rest = tokens[1:]
            if name.startswith("python") and "-m" in rest:
                k = rest.index("-m")
                if k + 1 < len(rest):
                    for arg in rest[:k]:
                        matches += _inline_matches(arg, ctx, depth)
                    tokens = rest[k + 1:]
                    continue
            for arg in rest:
                if _run_time_text(arg):
                    matches.append(_unreadable_match())
                matches += _inline_matches(arg, ctx, depth)
            for body in seg["heredocs"]:
                matches += _inline_matches(body, ctx, depth)
            if name == "expect":  # spawn/system/exec run their words as a command
                for text in rest + list(seg["heredocs"]):
                    for statement in re.split(r"[\n;]", text):
                        m = re.match(r"\s*(spawn|system|exec)\s+(.+)", statement)
                        if m:
                            matches += _shell_matches(m.group(2), ctx.fork(), depth + 1)
            operands = [a for a in rest if not a.startswith("-")]
            if seg["pipe_in"] and (not operands or operands[0] in ("-", "/dev/stdin")):
                matches.append(_unreadable_match())
            if operands and os.path.basename(operands[0]) == "dw":
                tokens = rest[rest.index(operands[0]):]
                continue
            break
        if name == "osascript":
            codes = [tokens[i + 1] for i, t in enumerate(tokens[:-1]) if t == "-e"]
            for code in codes + list(seg["heredocs"]):
                matches += _inline_matches(code, ctx, depth)
            break
        if name in ("awk", "gawk", "mawk", "nawk"):
            program = next(iter(_flags_values(tokens[1:], {"-F", "-v", "-f"})), "")
            if "-f" not in tokens and re.search(r"system\s*\(|\|\s*\"|\|&|getline", program):
                matches += _inline_matches(program, ctx, depth, spawn=True)
            break
        if name == "eval":
            body = " ".join(tokens[1:])
            if "$" in body or "`" in body or "__dwsub" in body:
                matches.append(_unreadable_match())
            else:
                matches += _shell_matches(body, ctx.fork(), depth + 1)
            tokens = []
            break
        if name in ("source", "."):
            target = tokens[1] if len(tokens) > 1 else ""
            if "__dwsub" in target or target in ("-", "/dev/stdin") or \
                    target.startswith("/dev/fd") or "://" in target or "$" in target:
                matches.append(_unreadable_match())
            break
        if name in WRAPPERS:
            matches += _wrapper_matches(tokens, seg, ctx, depth)
            tokens = []
            break
        if name in _RUNNERS and (not _RUNNERS[name] or tokens[1:2] and tokens[1] in _RUNNERS[name]):
            matches += _wrapper_matches(tokens, seg, ctx, depth, start=1 if not _RUNNERS[name] else 2)
            tokens = []
            break
        break
    if tokens and os.path.basename(tokens[0]) in ("cd", "pushd"):
        target = next((t for t in tokens[1:] if not t.startswith("-")), None)
        if target is None:
            ctx.cwd = os.path.realpath(_home())
        elif target == "-":
            ctx.cwd = None
        else:
            ctx.cwd = _resolve(target, ctx.cwd)
    if tokens and os.path.basename(tokens[0]) == "find":
        matches += _find_exec_matches(tokens, ctx, depth)
    matches += _control_matches(original, tokens, redirects, ctx)
    if tokens and os.path.basename(tokens[0]) == "git":
        matches += _git_control_matches(tokens, ctx)
    if tokens:
        rule = _first_rule(tokens, seg, ctx)
        if rule is not None:
            matches.append(_render(rule, " ".join(original)))
    return matches


def _find_exec_matches(tokens: list, ctx: _Ctx, depth: int) -> list:
    """Classify the commands that `find -exec/-execdir/-ok/-okdir` runs."""
    starts = []
    for t in tokens[1:]:
        if t.startswith("-") or t in ("(", "!", ")"):
            break
        starts.append(t)
    sample = (starts[0] if starts else ".").rstrip("/") + "/x"
    out = []
    i = 0
    while i < len(tokens):
        if tokens[i] in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            while j < len(tokens) and tokens[j] not in (";", "+"):
                j += 1
            inner = [sample if t == "{}" else t for t in tokens[i + 1:j]]
            if inner:
                out += _analyze(inner, [], _new_segment(False), ctx.fork(), depth + 1)
            i = j
        i += 1
    return out


# -- inline interpreter code ------------------------------------------------------

_INLINE_PATTERNS = [
    (re.compile(r"\bgit\s+push\b"), "inline-git-push", "merge", "push from inline code"),
    (re.compile(r"\b(gh\s+pr|glab\s+mr)\s+merge\b"), "inline-pr-merge", "merge",
     "merge a pull request from inline code"),
    (re.compile(r"\b(kubectl|oc)\b[^\n'\"]*\b(apply|create|replace|patch|delete|rollout|scale|"
                r"set|edit|drain)\b"), "inline-kubectl", "deploy", "change a cluster from inline code"),
    (re.compile(r"\bhelm\s+(install|upgrade|uninstall|delete|rollback|push)\b"), "inline-helm",
     "deploy", "change a Helm release from inline code"),
    (re.compile(r"\b(docker|podman)\s+((image|manifest|compose)\s+)?push\b"), "inline-docker-push",
     "deploy", "push an image from inline code"),
    (re.compile(r"\bvercel\b[^\n'\"]*(\bdeploy\b|--prod\b)"), "inline-vercel", "deploy",
     "deploy from inline code"),
    (re.compile(r"\b(netlify|firebase|wrangler|flyctl|fly|railway|serverless|sls)\s+(deploy|up)\b"),
     "inline-deploy", "deploy", "deploy from inline code"),
    (re.compile(r"\b(terraform|tofu|pulumi)\s+(apply|destroy|up)\b"), "inline-infra", "deploy",
     "change infrastructure from inline code"),
    (re.compile(r"\b(npm|pnpm|yarn|twine|cargo|gem|poetry|uv)\s+(publish|upload|push)\b"),
     "inline-publish", "publish", "publish a package from inline code"),
    (re.compile(r"\bgh\s+release\s+create\b"), "inline-release", "publish",
     "publish a release from inline code"),
    (_SQL_DESTRUCTIVE_RE, "inline-sql", "destroy", "destructive database command in inline code"),
    (re.compile(r"\b(sendmail|mailx|msmtp|swaks)\b|\bsmtplib\b|\bnodemailer\b|Net::SMTP"),
     "inline-mail", "send", "send email from inline code"),
    (re.compile(r"tell\s+application\s+\"(Messages|Mail|Microsoft Outlook|Slack|System Events)\"|"
                r"\bkeystroke\b", re.I), "inline-applescript-send", "send",
     "send a message or keystrokes from AppleScript"),
]
_SPAWN_RE = re.compile(
    r"subprocess|os\.system|os\.popen|os\.exec|os\.spawn|pty\.spawn|child_process|execSync|"
    r"spawnSync|\bexec(File)?\s*\(|\bspawn\s*\(|\bsystem\s*\(|`|\bpopen\s*\(|Popen|IO\.popen|"
    r"%x\{|shell_exec|passthru|proc_open|do shell script|Runtime\.getRuntime|Deno\.(run|Command)|"
    r"Bun\.spawn|commands\.getoutput|\$\(")
_GUARDED_NAME_RE = re.compile(
    r"(?<![\w.-])(git|gh|glab|kubectl|oc|helm|docker|podman|vercel|netlify|flyctl|wrangler|gcloud|"
    r"gsutil|aws|az|terraform|tofu|pulumi|twine|ssh|scp|rsync|psql|mysql|dropdb|sendmail|stripe|dw|"
    r"claude|agtermctl|curl|wget|nc)(?![\w.-])")
_DW_REF_RE = re.compile(
    r"(?<![\w.-])dw['\"]?\s*,?\s*['\"]?\s*(approve|deny|run|resume|cancel|dismiss|setup|hook|guard|"
    r"project['\"]?\s*,?\s*['\"]?\s*(add|remove))\b|(bin|control)/dw\b")
_LITERAL_RE = re.compile(r"'([^'\n]{1,2000})'|\"([^\"\n]{1,2000})\"")
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"]+")


def _inline_matches(text: str, ctx: _Ctx, depth: int, spawn: bool = False) -> list:
    """Matches for code given inline to an interpreter (python -c, node -e, a here-document...)."""
    out: list = []
    if depth > 6:
        return [_unreadable_match()]
    for m in _LITERAL_RE.finditer(text):
        literal = m.group(1) if m.group(1) is not None else m.group(2)
        if len(literal.split()) >= 2:
            out += [x for x in _shell_matches(literal, ctx.fork(), depth + 1)
                    if x["id"] != "control-unreadable"]
    found = {x["category"] for x in out}
    for rx, rid, category, describe in _INLINE_PATTERNS:
        if category not in found and rx.search(text):
            out.append({"id": rid, "category": category, "describe": "%s: %s" % (describe, _short(text))})
            found.add(category)
    if _DW_REF_RE.search(text):
        out.append({"id": "control-dw", "category": "control",
                    "describe": "change the control point: %s" % _short(text)})
    elif ctx.protected.text_hit(text):
        out.append(_state_match(text))
    if not out and (spawn or _SPAWN_RE.search(text)):
        remote = any(not _is_local_host(_url_host(u)) for u in _URL_RE.findall(text))
        if remote or _GUARDED_NAME_RE.search(text):
            out.append(_unreadable_match())
    return out


# -- git -----------------------------------------------------------------------------

_GIT_BUILTINS = set("""
add am annotate apply archive bisect blame branch bundle cat-file check-attr check-ignore
check-mailmap check-ref-format checkout checkout-index cherry cherry-pick citool clean clone
column commit commit-graph commit-tree config count-objects credential describe diff diff-files
diff-index diff-tree difftool fast-export fast-import fetch fetch-pack filter-branch
fmt-merge-msg for-each-ref for-each-repo format-patch fsck gc get-tar-commit-id grep gui
hash-object help hook index-pack init instaweb interpret-trailers log ls-files ls-remote ls-tree
mailinfo mailsplit maintenance merge merge-base merge-file merge-index merge-tree mergetool mktag
mktree multi-pack-index mv name-rev notes pack-objects pack-refs patch-id prune prune-packed pull
push range-diff read-tree rebase reflog remote repack replace request-pull rerere reset restore
rev-list rev-parse revert rm send-email shortlog show show-branch show-index show-ref
sparse-checkout stash status stripspace submodule switch symbolic-ref tag unpack-file
unpack-objects update-index update-ref update-server-info var verify-commit verify-pack
verify-tag version whatchanged worktree write-tree
""".split())
_GIT_ROUTING_KEY_RE = re.compile(
    r"^(alias\..+|remote\..+\.(push|url|pushurl)|remote\.pushdefault|push\..+|"
    r"url\..+\.(insteadof|pushinsteadof)|core\.sshcommand|core\.hookspath|"
    r"branch\..+\.(merge|remote|pushremote))$", re.I)
# The only keys `git -c` may set without a question; any other key can run commands or
# change where pushes go.
_GIT_HARMLESS_KEY_RE = re.compile(
    r"^(user\.(name|email)|color\.[A-Za-z0-9.-]+|core\.quotepath|advice\.[A-Za-z0-9]+|"
    r"init\.defaultbranch|core\.autocrlf)$", re.I)
_GIT_ROUTING_SECTION_RE = re.compile(r"^(alias|remote|push|url|branch)(\..*)?$|^core$", re.I)


def _git_config_value(repo: Optional[str], key: str, ctx: _Ctx, all_values: bool = False):
    """Local config read; (exit code, values). Code None when git could not run."""
    cache_key = ("config", repo, key, all_values)
    if cache_key not in ctx.git_cache:
        if repo is None:
            ctx.git_cache[cache_key] = (None, [])
        else:
            code, out = _git_call(repo, "config", "--get-all" if all_values else "--get", key)
            ctx.git_cache[cache_key] = (code, out.splitlines() if code == 0 else [])
    return ctx.git_cache[cache_key]


def _git_config_writes_routing(args: list) -> bool:
    value_opts = {"--file", "-f", "--blob", "--type", "--default", "--comment", "--value"}
    read_flags = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--list", "-l",
                  "--get-color", "--get-colorbool", "--show-origin", "--show-scope"}
    write_flags = {"--add", "--unset", "--unset-all", "--replace-all"}
    positional, flags = [], []
    i = 0
    while i < len(args):
        a = args[i]
        if a in value_opts:
            i += 2
            continue
        if a.startswith("-"):
            flags.append(a.split("=", 1)[0])
        else:
            positional.append(a)
        i += 1
    if any(f in ("--edit", "-e") for f in flags) or positional[:1] == ["edit"]:
        return True
    if any(f in ("--rename-section", "--remove-section") for f in flags) or \
            positional[:1] in (["rename-section"], ["remove-section"]):
        names = positional[1:] if positional[:1] in (["rename-section"], ["remove-section"]) \
            else positional
        return any(_GIT_ROUTING_SECTION_RE.match(n) for n in names)
    if positional[:1] in (["set"], ["unset"]):
        return len(positional) > 1 and bool(_GIT_ROUTING_KEY_RE.match(positional[1]))
    if positional[:1] in (["get"], ["list"]) or any(f in read_flags for f in flags):
        return False
    writing = any(f in write_flags for f in flags) or len(positional) >= 2
    return writing and bool(positional) and bool(_GIT_ROUTING_KEY_RE.match(positional[0]))


def _git_control_matches(tokens: list, ctx: _Ctx) -> list:
    """git forms that change where pushes go, or hide what runs."""
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "-c" and i + 1 < len(tokens):
            key = tokens[i + 1].split("=", 1)[0]
            if not _GIT_HARMLESS_KEY_RE.match(key):
                return [_unreadable_match()]
            i += 2
        elif t.startswith("--config-env"):
            return [_unreadable_match()]
        elif t in ("-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            break
    sub, args, repo, _unreadable = _git_parts(tokens, ctx)
    if sub is None:
        return []
    if _word_dynamic(sub):
        return [_unreadable_match()]
    if sub == "push" and any(_word_dynamic(a) for a in _push_parts(args)["positional"]):
        return [_unreadable_match()]
    if sub in ("config", "remote", "branch") and any(_word_dynamic(a) for a in args[:3]):
        return [_unreadable_match()]
    detail = " ".join(tokens)
    routing = {"id": "control-git-config", "category": "control",
               "describe": "change where git pushes go: %s" % _short(detail)}
    if sub == "config":
        return [routing] if _git_config_writes_routing(args) else []
    if sub == "remote":
        nonflags = [a for a in args if not a.startswith("-")]
        return [routing] if nonflags[:1] in (["set-url"], ["add"], ["rename"]) else []
    if sub == "branch":
        if any(a in ("-u", "--set-upstream-to", "--set-upstream") or
               a.startswith("--set-upstream-to=") for a in args):
            return [routing]
        return []
    if sub not in _GIT_BUILTINS:
        code, values = _git_config_value(repo, "alias." + sub, ctx)
        if code is None or code == 0:
            return [_unreadable_match()]
    return []


def _control_matches(original: list, tokens: list, redirects: list, ctx: _Ctx) -> list:
    out = []
    skip = None
    if not tokens:  # a wrapper: its suffixes were classified; spare a read-only dw program
        for i, t in enumerate(original):
            if os.path.basename(t) == "dw" and \
                    any(original[i + 1:i + 1 + len(a)] == a for a in DW_READ_ONLY):
                skip = i
    if tokens:
        name = os.path.basename(tokens[0])
        if name == "dw":
            if not any(tokens[1:1 + len(allowed)] == allowed for allowed in DW_READ_ONLY):
                out.append({"id": "control-dw", "category": "control",
                            "describe": "change the control point: %s" % _short(" ".join(tokens))})
            else:
                skip = len(original) - len(tokens) if original[-len(tokens):] == tokens else None
        elif name == "agtermctl":
            out.append({"id": "control-terminal", "category": "control",
                        "describe": "drive the terminal app: %s" % _short(" ".join(tokens))})
        elif name in AGENT_HARNESSES:
            out.append({"id": "control-agent", "category": "control",
                        "describe": "start another agent session outside the guard: %s"
                                    % _short(" ".join(tokens))})
    for i, token in enumerate(original):
        if i == skip:
            continue
        if ctx.protected.token_hit(token, ctx.cwd):
            out.append(_state_match(" ".join(original)))
            return out
    for target in redirects:
        if ctx.protected.token_hit(target, ctx.cwd):
            out.append(_state_match(" ".join(original)))
            return out
    return out


def _state_match(detail: str) -> dict:
    return {"id": "control-state", "category": "control",
            "describe": "change the control point's files: %s" % _short(detail)}


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _render(rule: dict, detail: str) -> dict:
    if rule["id"] == "control-unreadable":
        return _unreadable_match()
    return {"id": rule["id"], "category": rule["category"],
            "describe": "%s: %s" % (rule["describe"], _short(detail))}


_ALWAYS_SENSITIVE = {"git", "gh", "ssh", "scp", "rsync", "curl", "wget", "osascript", "dw",
                     "rm", "rmdir", "unlink", "shred", "trash", "srm", "find", "eval", "source", "."}


def sensitive_programs(rules: list) -> set:
    """Programs whose unreadable deciding words make a command `control` (see module doc)."""
    names = set(_ALWAYS_SENSITIVE) | set(SHELLS) | WRAPPERS | set(_RUNNERS) | SQL_CLIENTS
    names |= {"python", "python3", "pypy", "perl", "ruby", "node", "nodejs", "php", "deno", "bun"}
    for rule in rules:
        names |= set(rule.get("program") or ())
    return names


def _word_dynamic(word: str) -> bool:
    """A word whose value is only known when the command runs, or a pattern."""
    if word in ("[", "[[", "{", "}", "{}"):
        return False
    return _expand(word) is None or any(ch in word for ch in "*?[{")


def _unreadable_deciding_word(rule: dict, nonflags: list) -> bool:
    """Whether a rule's subcommand cannot be decided: the first operand is only known at run
    time, or a later one is while the operands before it begin one of the rule's subcommands."""
    def unreadable(w: str) -> bool:
        # A word with spaces was quoted, so it cannot glob; it can still hold a variable.
        return _expand(w) is None if re.search(r"\s", w) else _word_dynamic(w)

    sequences = [seq.split() for seq in rule.get("subcommand", [])] + \
        [[w] for w in rule.get("unless_subcommand", [])]
    for k, word in enumerate(nonflags[:max([len(q) for q in sequences] + [1])]):
        if not unreadable(word):
            continue
        if k == 0:
            return True
        before = nonflags[:k]
        if any(len(q) > k and all(fnmatch.fnmatchcase(w, p) for w, p in zip(before, q))
               for q in sequences):
            return True
    return False


def _first_rule(tokens: list, seg: dict, ctx: _Ctx) -> Optional[dict]:
    name = os.path.basename(tokens[0])
    nonflags = [t for t in tokens[1:] if not t.startswith("-")]
    undecided = None
    for rule in ctx.rules:
        if rule.get("tool") != "Bash":
            continue
        if _bash_rule_matches(rule, tokens, seg, ctx):
            return rule
        if undecided is None and name in (rule.get("program") or ()) and \
                ("subcommand" in rule or "unless_subcommand" in rule) and \
                _unreadable_deciding_word(rule, nonflags):
            undecided = _UNREADABLE_RULE  # a sensitive program's deciding word is unreadable
    return undecided


def _seq_matches(seq: list, words: list, within: int) -> bool:
    for start in range(0, min(within, len(words))):
        window = words[start:start + len(seq)]
        if len(window) == len(seq) and all(fnmatch.fnmatchcase(w, p) for w, p in zip(window, seq)):
            return True
    return False


def _bash_rule_matches(rule: dict, tokens: list, seg: dict, ctx: _Ctx) -> bool:
    name = os.path.basename(tokens[0])
    programs = rule.get("program")
    if programs and name not in programs:
        return False
    nonflags = [t for t in tokens[1:] if not t.startswith("-")]
    if "subcommand" in rule:
        within = int(rule.get("within", 3))
        if not any(_seq_matches(s.split(), nonflags, within) for s in rule["subcommand"]):
            return False
    if "unless_subcommand" in rule and nonflags and nonflags[0] in rule["unless_subcommand"]:
        return False
    if "args_any" in rule:
        if not any(t == a or t.startswith(a + "=") for t in tokens[1:] for a in rule["args_any"]):
            return False
    check = rule.get("check")
    if check:
        fn = _CHECKS.get(check)
        if fn is None:
            raise GuardError("unknown guard check: %s" % check)
        return bool(fn(tokens, seg, ctx))
    return bool(programs)


# -- checks used by the rules file -------------------------------------------


def _git_call(repo: str, *args, stderr: Optional[list] = None) -> tuple:
    """(exit code or None, stdout). Pass a list as `stderr` to receive git's error text."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        proc = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True,
                              timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    if stderr is not None:
        stderr.append(proc.stderr)
    return proc.returncode, proc.stdout.strip()


def _git_head(repo: Optional[str], ctx: _Ctx) -> tuple:
    """('branch', name) | ('detached', None) | ('norepo', None) | ('unknown', None)."""
    if repo is None:
        return "unknown", None
    key = ("head", repo)
    if key not in ctx.git_cache:
        err: list = []
        code, out = _git_call(repo, "symbolic-ref", "--short", "-q", "HEAD", stderr=err)
        if code == 0 and out:
            ctx.git_cache[key] = ("branch", out)
        elif code == 1:
            ctx.git_cache[key] = ("detached", None)
        elif code == 128 and "not a git repository" in "".join(err).lower():
            ctx.git_cache[key] = ("norepo", None)
        else:
            ctx.git_cache[key] = ("unknown", None)
    return ctx.git_cache[key]


def _protected_branches(repo: Optional[str], remote: Optional[str], ctx: _Ctx) -> set:
    names = {"main", "master"}
    if repo is None:
        return names
    remote = remote or "origin"
    key = ("default", repo, remote)
    if key not in ctx.git_cache:
        ctx.git_cache[key] = None
        if re.match(r"^[A-Za-z0-9._-]+$", remote):
            code, out = _git_call(repo, "symbolic-ref", "--short", "-q",
                                  "refs/remotes/%s/HEAD" % remote)
            if code == 0 and out.startswith(remote + "/"):
                ctx.git_cache[key] = out[len(remote) + 1:]
    if ctx.git_cache[key]:
        names.add(ctx.git_cache[key])
    return names


def _git_parts(tokens: list, ctx: _Ctx):
    """(subcommand, args, repo dir or None, unreadable)."""
    repo = ctx.cwd
    i = 1
    unreadable = False
    while i < len(tokens):
        t = tokens[i]
        if t == "-C" and i + 1 < len(tokens):
            repo = _resolve(tokens[i + 1], repo)
            i += 2
        elif t == "-c" and i + 1 < len(tokens):
            if tokens[i + 1].lower().startswith("alias."):
                unreadable = True
            i += 2
        elif t in ("--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"):
            repo = None
            i += 2
        elif t.startswith("--git-dir=") or t.startswith("--work-tree="):
            repo = None
            i += 1
        elif t.startswith("-"):
            i += 1
        else:
            break
    if i >= len(tokens):
        return None, [], repo, unreadable
    sub = tokens[i]
    if _dynamic(sub):
        unreadable = True
    return sub, tokens[i + 1:], repo, unreadable


def _push_parts(args: list) -> dict:
    value = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}
    out = {"all": False, "tags": False, "delete": False, "positional": []}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            out["positional"].extend(args[i + 1:])
            break
        if a in ("--all", "--mirror", "--branches"):
            out["all"] = True
        elif a in ("--tags", "--follow-tags"):
            out["tags"] = True
        elif a in ("-d", "--delete"):
            out["delete"] = True
        elif a in value:
            i += 1
        elif a.startswith("-"):
            pass
        else:
            out["positional"].append(a)
        i += 1
    return out


def _refspec_dst(ref: str, delete: bool) -> str:
    ref = ref.lstrip("+")
    if ":" in ref and not delete:
        src, dst = ref.split(":", 1)
        ref = dst or src
    elif ref.startswith(":"):
        ref = ref[1:]
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    return ref


def _check_git_push_default_branch(tokens, seg, ctx) -> bool:
    sub, args, repo, unreadable = _git_parts(tokens, ctx)
    if unreadable:
        return True  # an alias or a computed subcommand may well be a push
    if sub != "push":
        return False
    parts = _push_parts(args)
    if parts["all"] or ctx.incomplete:
        return True
    remote = parts["positional"][0] if parts["positional"] else None
    refspecs = parts["positional"][1:]
    if not refspecs:
        if parts["delete"]:
            return False
        return _implicit_push_reaches_default(repo, remote, ctx)
    for ref in refspecs:
        dst = _refspec_dst(ref, parts["delete"])
        if dst.startswith("refs/tags/"):
            continue
        if dst in ("HEAD", "@") or dst == "":
            if _implicit_push_reaches_default(repo, remote, ctx):
                return True
            continue
        if _dynamic(dst):
            return True
        if dst in ("main", "master") or dst in _protected_branches(repo, remote, ctx):
            return True
    return False


def _local_branches(repo: str, ctx: _Ctx) -> Optional[list]:
    key = ("branches", repo)
    if key not in ctx.git_cache:
        code, out = _git_call(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
        ctx.git_cache[key] = out.splitlines() if code == 0 else None
    return ctx.git_cache[key]


def _push_refspec_destinations(spec: str, current: Optional[str],
                               branches: list) -> Optional[set]:
    """Every branch a configured `remote.<name>.push` refspec would update; None when the
    refspec cannot be read."""
    spec = spec.lstrip("+")
    src, colon, dst = spec.partition(":")
    if not colon:
        dst = src
    out: set = set()

    def short(ref: str) -> Optional[str]:
        if ref.startswith("refs/tags/"):
            return None
        return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref

    if "*" in src or "*" in dst:
        if src.count("*") != 1 or dst.count("*") != 1:
            return None
        head, tail = src.split("*")
        for branch in branches:
            for name in ("refs/heads/" + branch, branch):
                if name.startswith(head) and name.endswith(tail) and \
                        len(name) >= len(head) + len(tail):
                    target = short(dst.replace("*", name[len(head):len(name) - len(tail)]))
                    if target:
                        out.add(target)
                    break
        return out
    if src in ("HEAD", "@"):
        if current is None:
            return None
        if not colon:
            dst = current
    target = short(dst)
    if target in ("HEAD", "@"):
        if current is None:
            return None
        target = current
    if target:
        out.add(target)
    return out


def _implicit_push_reaches_default(repo: Optional[str], remote: Optional[str], ctx: _Ctx) -> bool:
    """For a push without a destination branch: may it update the default branch, as far as
    the local git config shows? Unknown means yes. Never contacts the remote."""
    kind, branch = _git_head(repo, ctx)
    if kind == "norepo":
        return False
    if kind not in ("branch", "detached"):
        return True
    detached = kind == "detached"

    def get(key):
        code, values = _git_config_value(repo, key, ctx)
        if code not in (0, 1):
            raise LookupError(key)
        return values[0] if values else None

    try:
        upstream = None if detached else get("branch.%s.merge" % branch)
        if not remote:
            remote = (None if detached else get("branch.%s.pushRemote" % branch)) \
                or get("remote.pushDefault") \
                or (None if detached else get("branch.%s.remote" % branch)) or "origin"
        targets = set()
        if upstream:
            targets.add(upstream[len("refs/heads/"):] if upstream.startswith("refs/heads/")
                        else upstream)
        code, specs = _git_config_value(repo, "remote.%s.push" % remote, ctx, all_values=True)
        if code not in (0, 1):
            return True
        if specs:
            if detached:
                return True
            branches = _local_branches(repo, ctx)
            if branches is None:
                return True
            for spec in specs:
                if spec.startswith("^"):
                    continue
                found = _push_refspec_destinations(spec, branch, branches)
                if found is None:
                    return True
                targets |= found
        elif detached:
            mode = (get("push.default") or "simple").lower()
            return mode not in ("simple", "current", "upstream", "tracking", "nothing")
        else:
            mode = (get("push.default") or "simple").lower()
            if mode in ("current", "simple"):
                targets.add(branch)
            elif mode in ("upstream", "tracking"):
                if not upstream:
                    return False  # git refuses to push without an upstream
            elif mode != "nothing":
                return True  # matching, or a value this guard does not know
    except LookupError:
        return True
    return bool(targets & _protected_branches(repo, remote, ctx))


def _check_git_push_tags(tokens, seg, ctx) -> bool:
    sub, args, _repo, _u = _git_parts(tokens, ctx)
    if sub != "push":
        return False
    parts = _push_parts(args)
    return parts["tags"] or any(_refspec_dst(r, parts["delete"]).startswith("refs/tags/")
                                for r in parts["positional"][1:])


def _check_git_merge_default_branch(tokens, seg, ctx) -> bool:
    sub, args, repo, unreadable = _git_parts(tokens, ctx)
    if sub != "merge":
        return False
    if unreadable:
        return True
    if any(a in ("--abort", "--continue", "--quit", "--skip") for a in args):
        return False
    kind, branch = _git_head(repo, ctx)
    if kind == "branch":
        return branch in _protected_branches(repo, None, ctx)
    return kind == "unknown"


def _is_local_host(host: Optional[str]) -> bool:
    if not host:
        return False
    host = host.strip("[]").lower()
    return host in _LOCAL_HOSTS or host.startswith("127.") or host.endswith(".localhost")


def _url_host(url: str) -> Optional[str]:
    text = url if "://" in url else "http://" + url
    if text.startswith("http://:"):
        return "localhost"
    try:
        return urlsplit(text).hostname
    except ValueError:
        return None


_CURL_VALUE = {"-A", "-b", "-c", "-C", "-d", "-D", "-e", "-E", "-F", "-H", "-K", "-m", "-o", "-P",
               "-Q", "-r", "-T", "-u", "-U", "-w", "-x", "-X", "-y", "-Y", "-z", "--data",
               "--data-raw", "--data-binary", "--data-urlencode", "--data-ascii", "--json",
               "--form", "--form-string", "--header", "--request", "--output", "--user",
               "--user-agent", "--referer", "--cookie", "--cookie-jar", "--upload-file",
               "--write-out", "--proxy", "--config", "--cert", "--key", "--max-time",
               "--connect-timeout", "--retry", "--url", "--resolve", "--cacert", "--oauth2-bearer",
               "--range", "--continue-at", "--dump-header", "--limit-rate", "--max-filesize",
               "--unix-socket", "--interface", "--output-dir", "--variable", "--mail-rcpt",
               "--mail-from", "--retry-delay", "--retry-max-time", "--capath", "--ciphers",
               "--connect-to", "--expect100-timeout", "--keepalive-time", "--netrc-file",
               "--trace", "--trace-ascii", "--aws-sigv4", "--abstract-unix-socket"}
_CURL_WRITE = {"-d", "-F", "-T", "--data", "--data-raw", "--data-binary", "--data-urlencode",
               "--data-ascii", "--json", "--form", "--form-string", "--upload-file", "-K",
               "--config"}
_READ_METHODS = ("GET", "HEAD", "OPTIONS")


def _curl_options(tokens: list) -> tuple:
    """(options seen as {name: [values]}, positional urls)."""
    seen: dict = {}
    urls = []
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            urls.extend(tokens[i + 1:])
            break
        if t.startswith("--"):
            name, eq, val = t.partition("=")
            if eq:
                seen.setdefault(name, []).append(val)
            elif name in _CURL_VALUE:
                seen.setdefault(name, []).append(tokens[i + 1] if i + 1 < len(tokens) else "")
                i += 1
            else:
                seen.setdefault(name, [])
        elif t.startswith("-") and len(t) > 1:
            for k, ch in enumerate(t[1:], 1):
                flag = "-" + ch
                if flag in _CURL_VALUE:
                    val = t[k + 1:]
                    if not val:
                        val = tokens[i + 1] if i + 1 < len(tokens) else ""
                        i += 1
                    seen.setdefault(flag, []).append(val)
                    break
                seen.setdefault(flag, [])
        else:
            urls.append(t)
        i += 1
    urls += seen.get("--url", [])
    return seen, urls


def _check_http_write_remote(tokens, seg, ctx) -> bool:
    name = os.path.basename(tokens[0])
    if name == "curl":
        seen, urls = _curl_options(tokens)
        if "--unix-socket" in seen or "--abstract-unix-socket" in seen:
            return False
        methods = [m.upper() for m in seen.get("-X", []) + seen.get("--request", [])]
        write = any(f in seen for f in _CURL_WRITE) or any(m not in _READ_METHODS for m in methods)
    elif name == "wget":
        write = False
        urls = []
        value = {"-O", "-o", "-a", "-P", "-U", "-e", "-i", "-t", "-T", "-w", "-Q", "-l", "-D",
                 "--header", "--user", "--password", "--output-document", "--user-agent"}
        for t in tokens[1:]:
            opt = t.split("=", 1)[0]
            if opt in ("--post-data", "--post-file", "--body-data", "--body-file"):
                write = True
            if opt == "--method" and "=" in t and t.split("=", 1)[1].upper() not in _READ_METHODS:
                write = True
        if "--method" in tokens:
            k = tokens.index("--method")
            if k + 1 < len(tokens) and tokens[k + 1].upper() not in _READ_METHODS:
                write = True
        urls = _flags_values(tokens[1:], value)
    else:  # httpie and friends
        value = {"-a", "--auth", "--session", "--session-read-only", "-o", "--output", "--verify",
                 "--cert", "--cert-key", "--proxy", "--timeout", "-A", "--auth-type"}
        positional = _flags_values(tokens[1:], value)
        method = None
        if positional and re.fullmatch(r"[A-Z]+", positional[0]):
            method, positional = positional[0], positional[1:]
        urls = positional[:1]
        items = positional[1:]
        data_items = [it for it in items if re.match(r"^[^=:@]*(:=@|:=|=@|=|@)", it)
                      and not re.match(r"^[^=]*==", it)]
        write = (method is not None and method not in _READ_METHODS) or bool(data_items) or \
            any(t in ("-f", "--form", "--multipart", "--raw") for t in tokens[1:])
    if not write:
        return False
    if not urls:
        return True
    return any(not _is_local_host(_url_host(u)) for u in urls)


def _check_curl_mail(tokens, seg, ctx) -> bool:
    seen, urls = _curl_options(tokens)
    return "--mail-rcpt" in seen or any(u.lower().startswith(("smtp://", "smtps://")) for u in urls)


def _check_gh_api_write(tokens, seg, ctx) -> bool:
    nonflags = [t for t in tokens[1:] if not t.startswith("-")]
    if nonflags[:1] != ["api"]:
        return False
    for i, t in enumerate(tokens):
        opt, eq, val = t.partition("=")
        if opt in ("-X", "--method"):
            method = val if eq else (tokens[i + 1] if i + 1 < len(tokens) else "")
            if method.upper() not in _READ_METHODS:
                return True
        elif t.startswith("-X") and len(t) > 2 and t[2:].upper() not in _READ_METHODS:
            return True
        if opt in ("-f", "-F", "--field", "--raw-field", "--input"):
            return True
    return False


def _temp_roots() -> list:
    return [os.path.realpath(p) for p in ("/tmp", "/private/tmp")]


def _outside_project(target: str, ctx: _Ctx, root_ok: bool = False) -> bool:
    static = target
    if any(ch in static for ch in "*?[{"):
        static = re.split(r"[*?\[{]", static, 1)[0]
        static = static if static.endswith("/") or not static else os.path.dirname(static) or "."
    path = _resolve(static, ctx.cwd)
    if path is None:
        return True
    if ctx.project and _inside(path, ctx.project) and (root_ok or path != ctx.project):
        return False
    if any(path.startswith(root + "/") for root in _temp_roots()):
        return False
    return True


def _check_rm_outside_project(tokens, seg, ctx) -> bool:
    name = os.path.basename(tokens[0])
    if name in ("rm", "rmdir", "unlink", "shred", "trash", "srm"):
        targets = _flags_values(tokens[1:], set())
        if ctx.incomplete or not targets:
            return ctx.incomplete
        return any(_outside_project(t, ctx) for t in targets)
    if name == "find":
        deleting = "-delete" in tokens
        for i, t in enumerate(tokens):
            if t in ("-exec", "-execdir", "-ok", "-okdir") and i + 1 < len(tokens) and \
                    os.path.basename(tokens[i + 1]) in ("rm", "shred", "unlink", "rmdir"):
                deleting = True
        if not deleting:
            return False
        starts = []
        for t in tokens[1:]:
            if t.startswith("-") or t in ("(", "!", ")"):
                break
            starts.append(t)
        return any(_outside_project(t, ctx, root_ok=True) for t in (starts or ["."]))
    return False


def _check_sql_destructive(tokens, seg, ctx) -> bool:
    if not any(os.path.basename(t) in SQL_CLIENTS for t in tokens):
        return False
    text = "\n".join([ctx.full_text] + list(seg["heredocs"]))
    return bool(_SQL_DESTRUCTIVE_RE.search(text))


def _check_remote_copy(tokens, seg, ctx) -> bool:
    for t in tokens[1:]:
        if t.startswith("-") or "://" in t:
            continue
        if re.match(r"^([A-Za-z0-9._-]+@)?[A-Za-z0-9._-]+:", t) and not t.startswith((".", "/")):
            host = t.split(":", 1)[0].split("@")[-1]
            if not _is_local_host(host):
                return True
    return False


def _check_raw_network(tokens, seg, ctx) -> bool:
    positional = [t for t in tokens[1:] if not t.startswith("-")]
    return not any(_is_local_host(t) for t in positional)


def _check_osascript_beyond_notification(tokens, seg, ctx) -> bool:
    """Every osascript call is held, except one `-e 'display notification ...'` and nothing else."""
    if seg["pipe_in"] or seg["heredocs"] or seg["redirects"]:
        return True
    if len(tokens) != 3 or tokens[1] != "-e":
        return True
    code = tokens[2]
    if re.search(r"do\s+shell\s+script|run\s+script|\btell\b|\u00ab|\u00ac|[\r\n;]", code, re.I):
        return True
    return not re.match(r'^\s*display\s+notification\s+"[^"\\]*"(\s+with\s+title\s+"[^"\\]*")?'
                        r'(\s+subtitle\s+"[^"\\]*")?\s*$', code)


def _check_open_mail_app(tokens, seg, ctx) -> bool:
    apps = ("mail", "messages", "microsoft outlook", "outlook", "slack", "telegram", "whatsapp")
    for i, t in enumerate(tokens[1:], 1):
        low = t.lower()
        if low.startswith(("mailto:", "sms:", "imessage:", "slack:", "tg:", "whatsapp:")):
            return True
        if t in ("-a", "-b") and i + 1 < len(tokens) and \
                (tokens[i + 1].lower() in apps or "mail" in tokens[i + 1].lower()):
            return True
    return False


_CHECKS = {
    "open_mail_app": _check_open_mail_app,
    "osascript_beyond_notification": _check_osascript_beyond_notification,
    "git_push_default_branch": _check_git_push_default_branch,
    "git_push_tags": _check_git_push_tags,
    "git_merge_default_branch": _check_git_merge_default_branch,
    "http_write_remote": _check_http_write_remote,
    "curl_mail": _check_curl_mail,
    "gh_api_write": _check_gh_api_write,
    "rm_outside_project": _check_rm_outside_project,
    "sql_destructive": _check_sql_destructive,
    "remote_copy": _check_remote_copy,
    "raw_network": _check_raw_network,
}


# -- MCP tools ---------------------------------------------------------------

_SPEND_WORDS = {"purchase", "buy", "pay", "charge", "refund", "payout", "checkout", "subscribe",
                "transfer", "topup", "fund", "bid", "order"}
_SEND_WORDS = {"send", "reply", "forward", "invite", "notify", "respond", "email", "sms",
               "broadcast", "tweet", "dm"}
_WRITE_WORDS = {"create", "add", "update", "delete", "remove", "post", "publish", "share", "write",
                "put", "upload", "submit", "save", "set", "edit", "modify", "merge", "deploy",
                "schedule", "trash", "untrash", "archive", "move", "copy", "apply", "enqueue",
                "mark", "unmark", "label", "unlabel", "convert", "patch", "insert", "drop",
                "cancel", "approve", "reject", "assign", "close", "reopen", "restore", "rename",
                "install", "register", "start", "stop", "restart", "run", "execute", "trigger",
                "import", "sync", "push", "release", "launch", "revoke", "grant", "enable",
                "disable", "pin", "unpin", "like", "follow", "comment", "react", "spam", "clear",
                "destroy", "reset", "change", "manage", "generate", "train", "download_model",
                "commit", "store", "record", "upsert", "replace", "attach", "detach", "connect",
                "disconnect", "authorize", "authenticate", "complete", "batch", "call"}
_READ_WORDS = {"get", "list", "search", "find", "read", "fetch", "query", "describe", "lookup",
               "view", "show", "inspect", "explain", "details", "documentation", "docs",
               "analytics", "report", "reports", "stats", "statistics", "status", "info",
               "metadata", "context", "whoami", "preview", "check", "validate", "count",
               "download", "export", "retrieve", "browse", "scan", "summarize", "analyze",
               "compare", "calculate", "estimate", "suggest", "extract", "visualize", "plan",
               "planner", "guide", "help", "ping", "health", "version", "schema", "diff",
               "history", "snapshot", "navigate"}


def _tool_words(tool: str) -> list:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tool)
    return [w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w]


def tool_kind(tool: str) -> str:
    """'spend' | 'send' | 'write' | 'read' | 'unknown', from the words of an MCP tool name."""
    words = set(_tool_words(tool))
    if words & _SPEND_WORDS:
        return "spend"
    if words & _SEND_WORDS:
        return "send"
    if words & _WRITE_WORDS:
        return "write"
    if words & _READ_WORDS:
        return "read"
    return "unknown"


def _mcp_rule_matches(rule: dict, server: str, tool: str) -> bool:
    low = server.lower()
    if rule.get("server") and server not in rule["server"]:
        return False
    if rule.get("server_contains") and not any(s.lower() in low for s in rule["server_contains"]):
        return False
    if any(fnmatch.fnmatchcase(low, u.lower()) for u in rule.get("unless_server", [])):
        return False
    if rule.get("names") and tool not in rule["names"]:
        return False
    verbs = rule.get("verbs")
    if verbs:
        kind = tool_kind(tool)
        ok = {"write": kind in ("spend", "send", "write"), "write_or_unknown": kind != "read",
              "send": kind == "send", "spend": kind == "spend"}.get(verbs)
        if ok is None:
            raise GuardError("unknown verbs value in rule %s: %r" % (rule["id"], verbs))
        return ok
    return True


# -- classify ------------------------------------------------------------------


def _combine(matches: list) -> Optional[dict]:
    unique: list = []
    for m in matches:
        if not any(u["id"] == m["id"] for u in unique):
            unique.append(m)
    if not unique:
        return None
    if len(unique) == 1:
        return dict(unique[0])
    unique.sort(key=lambda m: CATEGORIES.index(m["category"]))
    return {"id": "+".join(m["id"] for m in unique), "category": unique[0]["category"],
            "describe": "; ".join(m["describe"] for m in unique)}


def classify(tool_name: str, tool_input: dict, cwd: str, project_path: str,
             rules: list) -> Optional[dict]:
    """The matching rule (`{"id", "category", "describe"}`) or None.

    `rules` may contain a `run_context(run_id)` entry; that run's result note is exempt
    from the control rules.
    """
    run_id = next((r["run_id"] for r in rules if "run_id" in r), None)
    rules = [r for r in rules if "run_id" not in r]
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    ctx = _Ctx(cwd, project_path, rules, run_id)
    shell_like = not tool_name.startswith("mcp__") and isinstance(tool_input.get("command"), str)
    if tool_name == "Bash" or (shell_like and tool_name not in WRITE_TOOLS):
        command = str(tool_input.get("command") or "")
        ctx.full_text = command
        return _combine(_shell_matches(command, ctx))
    if tool_name in WRITE_TOOLS:
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if target and ctx.protected.token_hit(str(target), ctx.cwd):
            return _state_match(str(target))
        return None
    if tool_name.startswith("mcp__"):
        server, _, tool = tool_name[len("mcp__"):].partition("__")
        for rule in rules:
            if rule.get("tool") == "mcp" and _mcp_rule_matches(rule, server, tool):
                return _render(rule, tool_name)
    return None


# -- finding the run -------------------------------------------------------------


def _project_for(run: dict, registry: dict) -> dict:
    for p in registry.get("projects", []):
        if p.get("id") == run.get("project_id"):
            return p
    pid = run.get("project_id") or "?"
    return {"id": pid, "name": pid, "path": run.get("project_path") or "", "guard_rules": []}


def _run_from_env() -> Optional[tuple]:
    run_id = os.environ.get("DW_RUN_ID")
    if not run_id:
        return None
    try:
        run = store.load_run(run_id)
    except store.RunNotFound:
        return None
    if run.get("state") not in runs.ACTIVE_STATES:
        return None
    return _project_for(run, store.load_registry()), run


def active_run_for_cwd(cwd: str) -> Optional[tuple]:
    """(project, run) when realpath(cwd) is inside a registered project with an active run."""
    real = os.path.realpath(cwd)
    projects = [p for p in store.load_registry().get("projects", [])
                if p.get("path") and _inside(real, p["path"])]
    if not projects:
        return None
    projects.sort(key=lambda p: len(p["path"]), reverse=True)
    records, corrupt = store.list_runs()
    for project in projects:
        mine = [r for r in records if r.get("project_id") == project["id"]
                and r.get("state") in runs.ACTIVE_STATES]
        if mine:
            mine.sort(key=lambda r: (r.get("started_at") or 0, r["id"]))
            return project, mine[0]
    if corrupt:
        raise GuardError("cannot tell whether a run is active: unreadable %s"
                         % ", ".join(str(p) for p in corrupt))
    return None


def _find_active(cwd: str) -> Optional[tuple]:
    return _run_from_env() or active_run_for_cwd(cwd)


def _probably_inside_run(cwd) -> bool:
    """After an error: whether the call may belong to an active run. Never raises."""
    try:
        run_id = os.environ.get("DW_RUN_ID")
        if run_id:
            try:
                if store.load_run(run_id).get("state") in runs.ACTIVE_STATES:
                    return True
            except store.CorruptFile:
                return True
            except store.RunNotFound:
                pass
        if not cwd:
            return False
        real = os.path.realpath(cwd)
        records, _corrupt = store.list_runs()
        active = [r for r in records if r.get("state") in runs.ACTIVE_STATES]
        if any(r.get("project_path") and _inside(real, r["project_path"]) for r in active):
            return True
        try:
            registry = store.load_registry()
        except Exception:
            return False
        ids = {r.get("project_id") for r in active}
        return any(p.get("path") and _inside(real, p["path"]) and p.get("id") in ids
                   for p in registry.get("projects", []))
    except Exception:
        return bool(os.environ.get("DW_RUN_ID"))


# -- the hook ------------------------------------------------------------------------


def _output(decision: str, reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": decision,
                                   "permissionDecisionReason": reason}}


def _fingerprint(tool: str, tool_input: dict) -> str:
    volatile = ("description", "timeout", "run_in_background")
    body = {k: v for k, v in tool_input.items() if k not in volatile}
    text = json.dumps([tool, body], sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def _ask_timeout() -> int:
    try:
        return int(os.environ.get("DW_GUARD_ASK_TIMEOUT") or ASK_TIMEOUT)
    except ValueError:
        return ASK_TIMEOUT


def _action_text(tool: str, tool_input: dict) -> str:
    if tool == "Bash":
        return str(tool_input.get("command") or "")
    if tool in WRITE_TOOLS:
        return str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    return json.dumps(tool_input, sort_keys=True, default=str)


def _matching_grant(grants: list, rule_id: str, action: str) -> Optional[dict]:
    for g in grants:
        if isinstance(g, dict) and g.get("rule") == rule_id and g.get("action") == action:
            return g
    return None


def _without(grants: list, grant: dict) -> list:
    out = list(grants)
    out.remove(grant)
    return out


def _try(event: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception as exc:  # a lost status or notification must not skip the hold
        events.log_error(event, exc)


def _hold(project: dict, run: dict, match: dict, tool: str, tool_input: dict) -> Optional[dict]:
    run_id = run["id"]
    action = _fingerprint(tool, tool_input)
    parts = match["id"].split("+")
    control = match["category"] == "control"
    describe = match["describe"]
    now = time.time()
    outcome: dict = {}

    def claim(r):
        if r.get("state") not in runs.ACTIVE_STATES:
            outcome["kind"] = "gone"
            return r
        if not control and all(p in (r.get("approvals") or []) for p in parts):
            outcome["kind"] = "approved"
            return r
        grants = list(r.get("grants") or [])
        grant = _matching_grant(grants, match["id"], action)
        if grant is not None:
            outcome["kind"] = "granted"
            return {**r, "grants": _without(grants, grant)}
        pending = r.get("pending_approval")
        if pending and pending.get("action") != action:
            outcome["kind"] = "busy"
            return r
        outcome["kind"] = "ask"
        if not pending:
            pending = {"rule": match["id"], "category": match["category"], "describe": describe,
                       "tool": tool, "action": action, "since": now}
        return runs._moved(r, now, state="blocked", reason="awaiting approval: " + describe,
                           pending_approval=pending)

    run = store.update_run(run_id, claim)
    kind = outcome["kind"]
    if kind in ("gone", "approved", "granted"):
        return None  # an approved action prints nothing: the harness's own flow decides
    if kind == "busy":
        return _output("deny", PENDING_REASON)

    sid = run.get("agterm_session")
    name = project.get("name") or project.get("id") or "?"
    answer = None
    error = None
    if not sid:
        error = GuardError("run %s has no AGTerm session to ask in" % run_id)
    else:
        _try("guard status", agterm.set_status, sid, "blocked")
        _try("guard notify", agterm.notify, sid, "dw: approval needed", "%s: %s" % (name, describe))
        buttons = [("once", "Approve once")]
        if not control:
            buttons.append(("run", "Approve for this run"))
        buttons.append(("deny", "Deny"))
        message = "%s\n\n%s: %s" % (describe, tool, _short(_action_text(tool, tool_input), 600))
        answer, error = _wait_for_owner(
            run_id, sid, "%s: approve %s?" % (name, match["category"]), message, buttons,
            lambda r: _decided_elsewhere(r, match["id"], parts, action, control))
    if answer == "run" and control:
        answer = "once"
    if answer not in ("once", "run", "deny"):
        answer = None

    result: dict = {}

    def settle(r):
        pending = r.get("pending_approval") or {}
        ours = pending.get("action") == action
        active = r.get("state") in runs.ACTIVE_STATES
        grants = list(r.get("grants") or [])
        if not active:
            result["out"] = _output("deny", "Guard error: run %s is no longer active" % run_id)
            return r
        approved = not control and all(p in (r.get("approvals") or []) for p in parts)
        if answer is None and approved:
            result["out"] = None
            result["answered"] = True
            if not ours:
                return r
            out = {**r, "pending_approval": None}
            if r.get("state") == "blocked" and \
                    str(r.get("reason") or "").startswith("awaiting approval"):
                out = runs._moved(out, time.time(), state="running", reason=None)
            return out
        if not ours:
            grant = _matching_grant(grants, match["id"], action)
            if grant is not None and answer != "deny":
                result["out"] = None
                result["answered"] = True
                return {**r, "grants": _without(grants, grant)}
            if pending == {}:
                result["answered"] = True
            result["out"] = _output("deny", DENIED_REASON if answer == "deny" or pending == {}
                                    else PENDING_REASON)
            return r
        if answer is None:
            if error is not None:
                result["out"] = _output("deny", "Guard error: %s" % _short(str(error) or
                                                                          error.__class__.__name__))
            else:
                result["out"] = _output("deny", PENDING_REASON)
            return r
        out = dict(r)
        out["pending_approval"] = None
        if r.get("state") == "blocked" and str(r.get("reason") or "").startswith("awaiting approval"):
            out = runs._moved(out, time.time(), state="running", reason=None)
        if answer == "run":
            out["approvals"] = list(r.get("approvals") or []) + \
                [p for p in parts if p not in (r.get("approvals") or [])]
        if answer == "deny":
            grant = _matching_grant(grants, match["id"], action)
            if grant is not None:
                out["grants"] = _without(grants, grant)
            result["out"] = _output("deny", DENIED_REASON)
        else:
            result["out"] = None
        result["answered"] = True
        return out

    store.update_run(run_id, settle)
    if result.get("answered") and sid:
        _try("guard status", agterm.set_status, sid, "active")
    return result["out"]


def _poll_interval() -> float:
    try:
        return max(0.01, float(os.environ.get("DW_GUARD_POLL_INTERVAL") or 1.0))
    except ValueError:
        return 1.0


def _decided_elsewhere(r: dict, rule_id: str, parts: list, action: str, control: bool) -> bool:
    """Whether the run record already settles a question that is still open: the run ended,
    `dw approve` left a grant, `dw deny` cleared it, or the rule was approved for the run."""
    if r.get("state") not in runs.ACTIVE_STATES:
        return True
    if (r.get("pending_approval") or {}).get("action") != action:
        return True
    if _matching_grant(list(r.get("grants") or []), rule_id, action) is not None:
        return True
    return not control and all(p in (r.get("approvals") or []) for p in parts)


def _wait_for_owner(run_id: str, sid: str, title: str, message: str, buttons: list,
                    settled) -> tuple:
    """Open the question without blocking, then poll it and the run record until one of them
    decides or the deadline passes. Returns (button id or None, error or None). The dialog
    is never left open."""
    ask_id = None
    error = None
    try:
        ask_id = agterm.ask_open(sid, title, message, buttons, default="deny")
    except agterm.AgtermError as exc:
        events.log_error("guard ask", exc)
        if "ask already pending" not in str(exc):
            return None, exc
    deadline = time.monotonic() + _ask_timeout()
    interval = _poll_interval()
    answer = None
    still_open = ask_id is not None
    try:
        while True:
            if still_open:
                state, button = agterm.ask_result(ask_id)
                if state == "answered":
                    answer, still_open = button, False
                    break
                if state == "cancelled":
                    still_open = False
                    break
            if settled(store.load_run(run_id)):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(interval)
    except Exception as exc:  # AGTerm or the record went away mid-wait
        events.log_error("guard wait", exc)
        error = exc
    finally:
        if still_open:
            _try("guard ask cancel", agterm.ask_cancel, ask_id)
    return answer, error


def decide(payload: dict) -> Optional[dict]:
    """The `PreToolUse` hook output object, or None to allow silently."""
    if not isinstance(payload, dict):
        raise GuardError("hook payload is not a JSON object")
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    cwd = payload.get("cwd")
    if not isinstance(tool, str) or not isinstance(cwd, str) or not cwd:
        raise GuardError("hook payload lacks tool_name or cwd")
    if not isinstance(tool_input, dict):
        tool_input = {}
    found = _find_active(cwd)
    if found is None:
        return None
    project, run = found
    rules = load_rules(project) + [run_context(run["id"])]
    match = classify(tool, tool_input, cwd, project.get("path") or cwd, rules)
    if match is None:
        return None
    return _hold(project, run, match, tool, tool_input)


def run_hook(stdin_text: str) -> Optional[dict]:
    """Everything `dw guard` does; never raises. Errors go to $DW_HOME/dw.log."""
    payload = None
    try:
        payload = json.loads(stdin_text)
        return decide(payload)
    except BaseException as exc:  # noqa: B902 - the hook must answer, never crash
        events.log_error("guard", exc)
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        if _probably_inside_run(cwd if isinstance(cwd, str) else None):
            message = " ".join(str(exc).split()) or exc.__class__.__name__
            return _output("deny", "Guard error: %s" % _short(message, 300))
        return None


# -- dw approve / dw deny ---------------------------------------------------------------


def _resolve_pending(run_id: str, grant: bool) -> dict:
    now = time.time()
    seen: dict = {}

    def fn(r):
        pending = r.get("pending_approval")
        if not pending:
            raise NothingPending("run %s has no pending approval" % run_id)
        if grant and (pending.get("category") == "control" or
                      str(pending.get("rule") or "").startswith("control-") or
                      "+control-" in str(pending.get("rule") or "")):
            raise ApprovalRefused(
                "%s changes the control point; it can be approved only in the run's own dialog"
                % pending.get("describe"))
        seen["pending"] = pending
        out = {**r, "pending_approval": None}
        if grant:
            out["grants"] = list(r.get("grants") or []) + [{
                "rule": pending.get("rule"), "action": pending.get("action"),
                "describe": pending.get("describe"), "granted_at": now}]
        if r.get("state") == "blocked" and str(r.get("reason") or "").startswith("awaiting approval"):
            out = runs._moved(out, now, state="running", reason=None)
        return out

    try:
        record = store.update_run(run_id, fn)
    except store.RunNotFound:
        raise NothingPending("unknown run: %s" % run_id)
    return {**record, "resolved": seen["pending"]}


def approve_pending(run_id: str) -> dict:
    """One-shot grant for the pending action; clears the pending approval."""
    return _resolve_pending(run_id, grant=True)


def deny_pending(run_id: str) -> dict:
    """Clear the pending approval without a grant."""
    return _resolve_pending(run_id, grant=False)


# -- install check ------------------------------------------------------------------------


def guard_entry_present(settings_path: Path) -> bool:
    """True when a `PreToolUse` hook command in the settings file runs `dw guard`."""
    try:
        with open(str(settings_path)) as fh:
            data = json.load(fh)
        groups = data["hooks"]["PreToolUse"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if not isinstance(groups, list):
        return False
    for group in groups:
        hooks = group.get("hooks") if isinstance(group, dict) else None
        for hook in hooks if isinstance(hooks, list) else []:
            command = hook.get("command") if isinstance(hook, dict) else None
            if not isinstance(command, str):
                continue
            try:
                argv = shlex.split(command)
            except ValueError:
                continue
            if len(argv) == 2 and os.path.basename(argv[0]) == "dw" and argv[1] == "guard":
                return True
    return False
