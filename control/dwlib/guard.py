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
import hashlib
import json
import os
import re
import shlex
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from . import agterm, events, paths, runs, store
from .guard_shell import (  # noqa: F401
    ANALYSIS_BUDGET,
    MAX_DEPTH,
    MAX_WRAPPER_TOKENS,
    SHELLS,
    WRAPPERS,
    _INTERPRETER_RE,
    _Lexer,
    _REMOTE_PARALLEL,
    _RUNNERS,
    _SHELL_STARTERS,
    _UNREADABLE_RULE,
    _Unreadable,
    _bounded_glob,
    _command_strings,
    _dynamic,
    _expand,
    _flags_values,
    _home,
    _inside,
    _new_segment,
    _resolve,
    _run_time_text,
    _short,
    _starts_shell_without_command,
    _strip_prefix,
    _tokens,
    _unquote,
    _unreadable_match,
    _word_dynamic,
)
from .guard_git import (  # noqa: F401
    _GIT_ENV_RE,
    _check_git_merge_default_branch,
    _check_git_push_default_branch,
    _check_git_push_tags,
    _git_control_matches,
)

CATEGORIES = ("control", "destroy", "spend", "send", "deploy", "merge", "publish")
# Spike B: a hook may wait at least this long (entry timeout 3600 s; 900 s was the longest probe).
HOOK_MAX_WAIT_SECONDS = 900
ASK_TIMEOUT = min(HOOK_MAX_WAIT_SECONDS - 30, 3000)

PENDING_REASON = ("Approval is pending with the owner. Do not work around it. "
                  "Continue other work, then retry this exact action later.")
DENIED_REASON = "Denied by the owner. Do not attempt this action another way."
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


def settings_path() -> Path:
    override = os.environ.get("DW_CLAUDE_SETTINGS")
    return Path(override) if override else Path(_home()) / ".claude" / "settings.json"


# Inside any .git directory (worktree and submodule git dirs included): the config, hooks and
# attributes files.
_GIT_INTERNAL_RE = re.compile(
    r"/\.git/(?:(?:worktrees|modules)/.+/)?(?:config|config\.worktree|info/attributes|hooks(?:/.*)?)$")


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
        if _GIT_INTERNAL_RE.search(path):
            return True  # git config, hooks and attributes decide what git runs and pushes
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

    def fork(self) -> "_Ctx":
        other = _Ctx.__new__(_Ctx)
        other.__dict__.update(self.__dict__)
        other.incomplete = False
        return other


def _string_matches(texts: list, ctx: _Ctx, depth: int) -> list:
    """Classify command strings in full, unreadable results included. A string the shell
    itself could not parse (unbalanced quotes) is not a command anything would run."""
    out: list = []
    for text in texts:
        try:
            _Lexer(text).run()
        except _Unreadable:
            continue
        out += _shell_matches(text, ctx.fork(), depth + 1)
    return out


# Option letters (and long options) whose value is code, per program family.
_CODE_LETTERS = {"python": "c", "pypy": "c", "perl": "eE", "ruby": "e", "node": "ep",
                 "nodejs": "ep", "bun": "ep", "deno": "", "php": "r", "lua": "e", "luajit": "e",
                 "Rscript": "e", "julia": "e", "expect": "c", "pwsh": "c", "powershell": "c"}
_CODE_LONG = ("--eval", "--print", "--command")


def _code_args(args: list, letters: str) -> list:
    """Values of the options that take code (-c CODE, -cCODE, -pe CODE, --eval=CODE)."""
    codes: list = []
    i = 0
    while i < len(args):
        t = args[i]
        if t == "--":
            break
        if t.startswith("--"):
            head, eq, val = t.partition("=")
            if head in _CODE_LONG:
                if eq:
                    codes.append(val)
                elif i + 1 < len(args):
                    codes.append(args[i + 1])
                    i += 1
        elif t.startswith("-") and len(t) > 1:
            k = next((k for k, ch in enumerate(t[1:], 1) if ch in letters), None)
            if k is not None:
                if t[k + 1:]:
                    codes.append(t[k + 1:])
                elif i + 1 < len(args):
                    codes.append(args[i + 1])
                    i += 1
        i += 1
    return codes


def _placeholders(name: str, tokens: list) -> set:
    """Words xargs or parallel replace with text read from standard input."""
    found = {"{}"}
    if name == "parallel":
        found |= {"{.}", "{/}", "{//}", "{/.}", "{#}", "{%}"}
    for i, t in enumerate(tokens[1:], 1):
        if t in ("-I", "--replace") and i + 1 < len(tokens):
            found.add(tokens[i + 1])
        elif t.startswith("-I") and len(t) > 2:
            found.add(t[2:])
        elif t.startswith(("--replace=", "-i")) and "=" in t:
            found.add(t.split("=", 1)[1])
    return {p for p in found if p}


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
    if incomplete:  # text from standard input replaces these words: unreadable
        marks = sorted(_placeholders(name, tokens), key=len, reverse=True)
        replaced = []
        for t in tokens:
            for mark in marks:
                t = t.replace(mark, "__dwsub_input__")
            replaced.append(t)
        tokens = replaced
    inner_seg = seg
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
            # The -c value (or the first operand, the script file) is the code. A run-time
            # value there cannot be read; later operands are data for the script.
            args = tokens[1:]
            codes = _code_args(args, "c")
            operands = [a for a in args if not a.startswith(("-", "+"))]
            for code in codes:
                if _run_time_text(code) or "__dwsub" in code:
                    matches.append(_unreadable_match())
                else:
                    matches += _string_matches([code], ctx, depth)
            if not codes and operands and _run_time_text(operands[0]):
                matches.append(_unreadable_match())  # the script itself is computed
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
            family = re.sub(r"[0-9.]+$", "", name)
            codes = _code_args(rest, _CODE_LETTERS.get(family, "ce"))
            operands = [a for a in rest if not a.startswith("-")]
            for code in codes:
                if _run_time_text(code) or "__dwsub" in code:
                    matches.append(_unreadable_match())
            if not codes and operands and _run_time_text(operands[0]):
                matches.append(_unreadable_match())  # the script itself is computed
            for arg in rest:
                matches += _inline_matches(arg, ctx, depth)
            for body in seg["heredocs"]:
                matches += _inline_matches(body, ctx, depth)
            if name == "expect":  # spawn/system/exec anywhere run their words as a command
                for text in rest + list(seg["heredocs"]):
                    found = []
                    for m in re.finditer(r"\b(spawn|system|exec)\s+((?:-\w+\s+)*)([^;\n}\]]+)", text):
                        found += _shell_matches(m.group(3), ctx.fork(), depth + 1)
                    if not found and re.search(r"\b(spawn|system|exec)\b", text) and \
                            _GUARDED_NAME_RE.search(text):
                        found.append(_unreadable_match())
                    matches += found
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
    if tokens and os.path.basename(tokens[0]) == "gh":
        matches += _gh_control_matches(tokens)
    if tokens:
        rule = _first_rule(tokens, seg, ctx)
        if rule is not None:
            matches.append(_render(rule, " ".join(original)))
    return matches


_GH_COMMANDS = set("""
agent-task alias api attestation auth browse cache co codespace completion config copilot
extension ext gist gpg-key help issue label org pr preview project release repo ruleset run
search secret ssh-key status variable workflow version
""".split())


def _gh_control_matches(tokens: list) -> list:
    """gh aliases run arbitrary gh commands; extensions are code this guard cannot read."""
    words = []
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in ("-R", "--repo"):
            i += 2
            continue
        if not t.startswith("-"):
            words.append(t)
        i += 1
    if not words:
        return []
    if words[0] == "alias" and words[1:2] in (["set"], ["import"]):
        return [{"id": "control-gh-alias", "category": "control",
                 "describe": "define a gh alias: %s" % _short(" ".join(tokens))}]
    if words[0] not in _GH_COMMANDS:
        return [_unreadable_match()]
    return []


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
    if undecided is None and ctx.incomplete:
        # More words arrive from standard input: if the deciding ones may be among them, the
        # command cannot be read.
        lengths = [len(seq.split()) for r in ctx.rules if r.get("tool") == "Bash"
                   and name in (r.get("program") or ()) for seq in r.get("subcommand", [])]
        if name in ("git", "gh"):
            lengths.append(1)
        if lengths and len(nonflags) < max(lengths):
            undecided = _UNREADABLE_RULE
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


def _try(event: str, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # a lost status or notification must not skip the hold
        events.log_error(event, exc)


_CLOCK: dict = {"start": None}  # when the current hook call began (set by run_hook)


def _hook_limit() -> float:
    """Seconds from hook start by which everything, trailing calls included, is done."""
    try:
        return float(os.environ.get("DW_GUARD_HOOK_LIMIT") or HOOK_MAX_WAIT_SECONDS - 10)
    except ValueError:
        return HOOK_MAX_WAIT_SECONDS - 10


def _time_left(start: float) -> float:
    return start + _hook_limit() - time.monotonic()


def _bounded(event: str, start: float, fn, *args, **kwargs) -> None:
    """Call an AGTerm function with a timeout that fits the hook limit; failures are logged."""
    left = _time_left(start)
    if left <= 0.2:
        events.log_error(event, GuardError("no time left for this call"))
        return
    _try(event, fn, *args, timeout=min(5.0, left - 0.1), **kwargs)


def _hold(project: dict, run: dict, match: dict, tool: str, tool_input: dict) -> Optional[dict]:
    started = _CLOCK["start"] or time.monotonic()
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
        _bounded("guard status", started, agterm.set_status, sid, "blocked")
        _bounded("guard notify", started, agterm.notify, sid, "dw: approval needed",
                 "%s: %s" % (name, describe))
        buttons = [("once", "Approve once")]
        if not control:
            buttons.append(("run", "Approve for this run"))
        buttons.append(("deny", "Deny"))
        message = "%s\n\n%s: %s" % (describe, tool, _short(_action_text(tool, tool_input), 600))
        answer, error = _wait_for_owner(
            run_id, sid, "%s: approve %s?" % (name, match["category"]), message, buttons,
            lambda r: _decided_elsewhere(r, match["id"], parts, action, control), started)
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
            last = r.get("last_decision") or {}
            denied = answer == "deny" or (pending == {} and last.get("action") == action
                                          and last.get("answer") == "deny")
            result["out"] = _output("deny", DENIED_REASON if denied else PENDING_REASON)
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
        out["last_decision"] = {"action": action, "answer": answer, "at": time.time()}
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
        _bounded("guard status", started, agterm.set_status, sid, "active")
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
                    settled, started: float) -> tuple:
    """Open the question without blocking, then poll it and the run record until one of them
    decides or the deadline passes. Returns (button id or None, error or None). The dialog
    is never left open."""
    ask_id = None
    error = None
    deadline = started + _ask_timeout()  # measured from hook start

    def call_timeout() -> float:
        left = _time_left(started)
        if left <= 0.2:
            raise GuardError("the hook time limit was reached")
        return min(5.0, left - 0.1)

    try:
        ask_id = agterm.ask_open(sid, title, message, buttons, default="deny",
                                 timeout=call_timeout())
    except (agterm.AgtermError, GuardError) as exc:
        events.log_error("guard ask", exc)
        if "ask already pending" not in str(exc):
            return None, exc
    interval = _poll_interval()
    answer = None
    still_open = ask_id is not None
    try:
        while True:
            if still_open:
                state, button = agterm.ask_result(ask_id, timeout=call_timeout())
                if state == "answered":
                    answer, still_open = button, False
                    break
                if state == "cancelled":
                    still_open = False
                    break
            if settled(store.load_run(run_id)):
                break
            now = time.monotonic()
            if now >= deadline or _time_left(started) <= 0.5:
                break
            time.sleep(max(0.0, min(interval, deadline - now)))
    except Exception as exc:  # AGTerm or the record went away mid-wait
        events.log_error("guard wait", exc)
        error = exc
    finally:
        if still_open:
            _bounded("guard ask cancel", started, agterm.ask_cancel, ask_id)
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
    _CLOCK["start"] = time.monotonic()
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
        out = {**r, "pending_approval": None,
               "last_decision": {"action": pending.get("action"),
                                 "answer": "approve" if grant else "deny", "at": now}}
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
