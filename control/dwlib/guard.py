"""Approval guard: the `PreToolUse` hook that holds a run's risky actions for the owner.

`dw guard` reads the hook payload on stdin. Outside an active run it allows silently.
Inside one, an action that matches a rule is held: the run is marked blocked, the owner
is asked through AGTerm, and the answer allows or denies the tool call.
"""
from __future__ import annotations

import fnmatch
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

    def token_hit(self, token: str, cwd: Optional[str]) -> bool:
        candidates = [token]
        if "=" in token:
            candidates.append(token.split("=", 1)[1])
        for cand in candidates:
            if not cand or len(cand) > 4096:
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


def _tokens(words: list) -> list:
    out = []
    for w in words:
        try:
            parts = shlex.split(w)
        except ValueError:
            raise _Unreadable("quoting")
        out.append(" ".join(parts) if parts else "")
    return out


# -- shell analysis ----------------------------------------------------------

SHELLS = ("sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh")
_INTERPRETER_RE = re.compile(r"^(python[0-9.]*|pypy[0-9.]*|perl|ruby|node|nodejs|php|deno|bun)$")
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

    def fork(self) -> "_Ctx":
        other = _Ctx.__new__(_Ctx)
        other.__dict__.update(self.__dict__)
        other.incomplete = False
        return other


def _unreadable_match() -> dict:
    return {"id": "control-unreadable", "category": "control", "describe": UNREADABLE}


def _dynamic(token: str) -> bool:
    if token in ("[", "[["):
        return False
    return _expand(token) is None or any(ch in token for ch in "*?[")


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


_WRAPPER_VALUE_OPTS = {
    "builtin": (), "nohup": (), "chronic": (), "unbuffer": (), "time": ("-f", "-o"),
    "exec": ("-a",), "nice": ("-n", "--adjustment"), "ionice": ("-c", "-n", "-p"),
    "caffeinate": ("-t", "-w"), "stdbuf": ("-i", "-o", "-e"), "watch": ("-n", "--interval"),
    "dotenv": ("-e", "-f", "-v", "-c"),
}


def _unwrap(tokens: list, ctx: _Ctx):
    """Strip one wrapper (env, sudo, nohup, ...). Returns new tokens, a script string for
    `env -S`, or None when `tokens[0]` is not a wrapper."""
    name = os.path.basename(tokens[0])
    if name == "env":
        i = 1
        while i < len(tokens):
            t = tokens[i]
            if t in ("-u", "--unset"):
                i += 2
            elif t in ("-C", "--chdir"):
                ctx.cwd = _resolve(tokens[i + 1], ctx.cwd) if i + 1 < len(tokens) else None
                i += 2
            elif t in ("-S", "--split-string"):
                return ("script", " ".join(tokens[i + 1:]))
            elif t.startswith("-S") and len(t) > 2:
                return ("script", " ".join([t[2:]] + tokens[i + 1:]))
            elif t == "--":
                i += 1
                break
            elif t.startswith("-") or _ASSIGNMENT_RE.match(t):
                i += 1
            else:
                break
        return tokens[i:]
    if name in ("sudo", "doas"):
        value = {"-u", "-g", "-h", "-p", "-U", "-C", "-D", "-r", "-t", "-T", "--user", "--group",
                 "--host", "--prompt", "--chdir", "--role", "--type", "--close-from",
                 "--other-user", "--command-timeout"}
        i = 1
        while i < len(tokens):
            t = tokens[i]
            if t in ("-D", "--chdir") and i + 1 < len(tokens):
                ctx.cwd = _resolve(tokens[i + 1], ctx.cwd)
            if t == "--":
                i += 1
                break
            if t in value:
                i += 2
            elif t.startswith("-") or _ASSIGNMENT_RE.match(t):
                i += 1
            else:
                break
        return tokens[i:]
    if name == "command":
        if any(t in ("-v", "-V") for t in tokens[1:2]):
            return []
        return tokens[_skip_options(tokens, 1):]
    if name in _WRAPPER_VALUE_OPTS:
        return tokens[_skip_options(tokens, 1, _WRAPPER_VALUE_OPTS[name]):]
    if name in ("timeout", "gtimeout"):
        i = _skip_options(tokens, 1, {"-s", "-k", "--signal", "--kill-after"})
        return tokens[i + 1:]
    if name == "xargs":
        ctx.incomplete = True
        value = {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "--max-args", "--max-procs",
                 "--delimiter", "--arg-file", "--replace"}
        return tokens[_skip_options(tokens, 1, value):]
    if name in ("npx", "bunx", "pnpx"):
        return tokens[_skip_options(tokens, 1, {"-p", "--package", "-c", "--call"}):]
    if name in ("pnpm", "yarn", "npm", "uv", "poetry", "pipenv", "bundle", "op", "rye", "pdm",
                "hatch") and len(tokens) > 1:
        runner = {"pnpm": ("dlx", "exec"), "yarn": ("dlx", "exec"), "npm": ("exec", "x"),
                  "uv": ("run",), "poetry": ("run",), "pipenv": ("run",), "bundle": ("exec",),
                  "op": ("run",), "rye": ("run",), "pdm": ("run",), "hatch": ("run",)}[name]
        if tokens[1] in runner:
            return tokens[_skip_options(tokens, 2, {"--with", "--package", "-p", "--env-file"}):]
    return None


def _shell_script(tokens: list):
    """For `bash -c SCRIPT`: (SCRIPT, rest); (None, rest) when there is no -c, where rest
    are the arguments after the shell's options."""
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            i += 2
        elif t == "--":
            return None, tokens[i + 1:]
        elif len(t) > 1 and t[0] in "-+" and not t.startswith("--"):
            if t[0] == "-" and "c" in t[1:]:
                return (tokens[i + 1] if i + 1 < len(tokens) else ""), []
            i += 1
        elif t.startswith("--"):
            i += 1
        else:
            break
    return None, tokens[i:]


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
    ctx.incomplete = False
    matches: list = []
    tokens = original
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
            script, args = _shell_script(tokens)
            if script is not None:
                matches += _shell_matches(script, ctx.fork(), depth + 1)
            else:
                stdin_program = not args or args[0] in ("-", "/dev/stdin") or "-s" in tokens
                if (args and "__dwsub" in args[0]) or (stdin_program and seg["pipe_in"]):
                    matches.append(_unreadable_match())
                elif stdin_program:
                    for body in seg["heredocs"]:
                        matches += _shell_matches(body, ctx.fork(), depth + 1)
            tokens = []
            break
        if _INTERPRETER_RE.match(name):
            value = {"-W", "-X", "-I", "-r", "--require", "-M"}
            rest = tokens[1:]
            if name.startswith("python") and "-m" in rest:
                k = rest.index("-m")
                if k + 1 < len(rest):
                    tokens = rest[k + 1:]
                    continue
            inline = any(t in ("-c", "-e", "-E", "--eval", "-p", "--print") for t in rest)
            positional = _flags_values(rest, value)
            if not inline:
                stdin_program = not positional or positional[0] in ("-", "/dev/stdin")
                if (positional and "__dwsub" in positional[0]) or \
                        (stdin_program and seg["pipe_in"]):
                    matches.append(_unreadable_match())
            if positional and os.path.basename(positional[0]) == "dw":
                tokens = rest[rest.index(positional[0]):]
                continue
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
        unwrapped = _unwrap(tokens, ctx)
        if unwrapped is None:
            break
        if isinstance(unwrapped, tuple):
            matches += _shell_matches(unwrapped[1], ctx.fork(), depth + 1)
            tokens = []
            break
        tokens = unwrapped
    if tokens and os.path.basename(tokens[0]) in ("cd", "pushd"):
        target = next((t for t in tokens[1:] if not t.startswith("-")), None)
        if target is None:
            ctx.cwd = os.path.realpath(_home())
        elif target == "-":
            ctx.cwd = None
        else:
            ctx.cwd = _resolve(target, ctx.cwd)
    matches += _control_matches(original, tokens, redirects, ctx)
    if tokens:
        rule = _first_rule(tokens, seg, ctx)
        if rule is not None:
            matches.append(_render(rule, " ".join(original)))
    return matches


def _control_matches(original: list, tokens: list, redirects: list, ctx: _Ctx) -> list:
    out = []
    skip = None
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
    return {"id": rule["id"], "category": rule["category"],
            "describe": "%s: %s" % (rule["describe"], _short(detail))}


def _first_rule(tokens: list, seg: dict, ctx: _Ctx) -> Optional[dict]:
    for rule in ctx.rules:
        if rule.get("tool") != "Bash":
            continue
        if _bash_rule_matches(rule, tokens, seg, ctx):
            return rule
    return None


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


def _git_call(repo: str, *args) -> tuple:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        proc = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True,
                              timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return proc.returncode, proc.stdout.strip()


def _git_head(repo: Optional[str], ctx: _Ctx) -> tuple:
    """('branch', name) | ('detached', None) | ('norepo', None) | ('unknown', None)."""
    if repo is None:
        return "unknown", None
    key = ("head", repo)
    if key not in ctx.git_cache:
        code, out = _git_call(repo, "symbolic-ref", "--short", "-q", "HEAD")
        if code == 0 and out:
            ctx.git_cache[key] = ("branch", out)
        elif code == 1:
            ctx.git_cache[key] = ("detached", None)
        elif code == 128:
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
        kind, branch = _git_head(repo, ctx)
        if kind == "branch":
            return branch in _protected_branches(repo, remote, ctx)
        return kind == "unknown"
    for ref in refspecs:
        dst = _refspec_dst(ref, parts["delete"])
        if dst.startswith("refs/tags/"):
            continue
        if dst in ("HEAD", "@") or dst == "":
            kind, branch = _git_head(repo, ctx)
            if kind == "unknown" or (kind == "branch" and
                                     branch in _protected_branches(repo, remote, ctx)):
                return True
            continue
        if _dynamic(dst):
            return True
        if dst in ("main", "master") or dst in _protected_branches(repo, remote, ctx):
            return True
    return False


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
    if any(ch in static for ch in "*?["):
        static = re.split(r"[*?\[]", static, 1)[0]
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


_CHECKS = {
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
    if kind == "gone":
        return None
    if kind == "approved":
        return _output("allow", "Approved by the owner for this run.")
    if kind == "granted":
        return _output("allow", "Approved once by the owner.")
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
        try:
            answer = agterm.ask(sid, "%s: approve %s?" % (name, match["category"]), message,
                                buttons, _ask_timeout(), default="deny")
        except agterm.AgtermError as exc:
            if "ask already pending" not in str(exc):
                error = exc
            events.log_error("guard ask", exc)
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
        if not ours:
            grant = _matching_grant(grants, match["id"], action)
            if grant is not None and answer != "deny":
                result["out"] = _output("allow", "Approved once by the owner.")
                return {**r, "grants": _without(grants, grant)}
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
            result["out"] = _output("allow", "Approved by the owner%s."
                                    % (" for this run" if answer == "run" else " once"))
        result["answered"] = True
        return out

    store.update_run(run_id, settle)
    if result.get("answered") and sid:
        _try("guard status", agterm.set_status, sid, "active")
    return result["out"]


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
