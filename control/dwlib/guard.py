"""Approval guard: the `PreToolUse` hook that holds a run's risky actions for the owner.

`dw guard` reads the hook payload on stdin. Outside an active run it allows silently.
Inside one, an action that matches a rule is held: the run is marked blocked, the owner
is asked through AGTerm, and the answer allows or denies the tool call. A session whose
`DW_RUN_ID` names a run that is no longer active (and no other run is active where it works)
is refused every matching action outright, without asking.

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
import ipaddress
import json
import os
import posixpath
import re
import shlex
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from . import agterm, events, paths, runs, store
from .guard_shell import (  # noqa: F401
    ANALYSIS_BUDGET,
    _ASSIGNMENT_RE,
    MAX_DEPTH,
    MAX_WRAPPER_TOKENS,
    SHELLS,
    WRAPPERS,
    _INTERPRETER_RE,
    _Lexer,
    _TooMany,
    _brace_expand,
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
from .guard_paths import (  # noqa: F401
    MAX_WILDCARDS,
    _ANY,
    _AWK,
    _DIGEST,
    _DW_HOME_VAR_RE,
    _GIT_ANY,
    _GIT_DIR_CHILDREN,
    _GIT_DIR_SUB_RE,
    _GIT_DIR_VAR_RE,
    _GIT_FILES,
    _GIT_FILES_RE,
    _GIT_INTERNAL_RE,
    _GIT_PATH_SUB_RE,
    _GLOB_PART_RE,
    _LESS,
    _PROTECTED_NAMES,
    _Protected,
    _READ_ONLY,
    _RUN_TIME_MARKS_RE,
    _RUN_TIME_PART_RE,
    _SED_ADDRESS,
    _SED_SCRIPT_RE,
    _WILD_PART_RE,
    _awk_program_only_prints,
    _could_be,
    _is_option,
    _may_be_path,
    _may_equal,
    _read_only,
    _run_time,
    _sed_scripts_only_print,
    _segment_regex,
    _wild,
    _wildcards,
    settings_path,
)
from .guard_git import (  # noqa: F401
    _GIT_ENV_RE,
    _check_git_merge_default_branch,
    _git_parts,
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
INACTIVE_REASON = ("Run %s is %s; guarded actions are refused in this session. "
                   "The owner can do this by hand or start a new run.")
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
        self.sub_bodies: list = []  # what the substitutions of the command being read run
        self.marks: tuple = ()  # replace strings of the xargs, parallel or find running this
        self.loop_words: dict = {}  # loop variable -> the words it runs over
        self.stdin_commands: list = []  # the commands piped into the one being read, as words
        self.budget = {"left": ANALYSIS_BUDGET}  # shared by every fork of this context

    def fork(self) -> "_Ctx":
        other = _Ctx.__new__(_Ctx)
        other.__dict__.update(self.__dict__)
        other.incomplete = False
        return other


_APOSTROPHE_TEXT_RE = re.compile(r"[A-Za-z]'[A-Za-z]")
_SHELL_SYNTAX_RE = re.compile(r"[$`;|&<>()\\\n{}]")


def _prose_with_apostrophe(text: str, exc: Exception) -> bool:
    """A string that fails to lex only because it is prose with an apostrophe ("it's done"),
    with no other shell syntax: not a command anything would run."""
    return str(exc) == "unterminated quote" and text.count("'") % 2 == 1 and \
        bool(_APOSTROPHE_TEXT_RE.search(text)) and \
        not _SHELL_SYNTAX_RE.search(text.replace("__dwsub", "")) and '"' not in text


def _string_matches(texts: list, ctx: _Ctx, depth: int) -> list:
    """Classify command strings in full, unreadable results included. A string that cannot be
    lexed is unreadable, unless it is plain prose with an apostrophe."""
    out: list = []
    for text in texts:
        try:
            _Lexer(text).run()
        except _Unreadable as exc:
            if not _prose_with_apostrophe(re.sub(r"__dwsub\w*?__", "", text), exc):
                out.append(_unreadable_match())
            continue
        out += _shell_matches(text, ctx.fork(), depth + 1)
    return out


# Option letters (and long options) whose value is code, per program family.
_CODE_LETTERS = {"python": "c", "pypy": "c", "perl": "eE", "ruby": "e", "node": "ep",
                 "bun": "ep", "deno": "", "php": "r", "lua": "e", "luajit": "e",
                 "Rscript": "e", "julia": "e", "expect": "c", "pwsh": "c", "powershell": "c"}
_CODE_LONG = ("--eval", "--print", "--command")


# Option letters (and long options) whose value names code to load before the script runs.
_LOADER_LETTERS = {"perl": "Mm", "ruby": "r", "node": "r", "bun": "r", "python": "m", "pypy": "m"}
_NODE_LOADERS = ("--require", "--import", "--loader", "--experimental-loader", "--preload")
_LOADER_LONG = {"node": _NODE_LOADERS, "bun": _NODE_LOADERS, "deno": _NODE_LOADERS,
                "ruby": ("--require",)}
_FAMILY_ALIASES = {"nodejs": "node", "tsx": "node", "ts-node": "node"}


def _loader_args(args: list, family: str) -> list:
    """Values of the options that load code (perl -MMod, ruby -rlib/--require, python -mmod,
    node -r/--require/..., bun --preload), anywhere on the line: which options take a
    separate value is not modelled."""
    letters = _LOADER_LETTERS.get(family, "")
    long_options = _LOADER_LONG.get(family, ())
    found: list = []
    i = 0
    while i < len(args):
        t = args[i]
        if t == "--":
            break
        if t.startswith("--"):
            head, eq, val = t.partition("=")
            if head in long_options:
                if eq:
                    found.append(val)
                elif i + 1 < len(args):
                    found.append(args[i + 1])
                    i += 1
        elif t.startswith("-") and not t.startswith("--") and len(t) > 1 and t[1] in letters:
            if t[2:]:
                found.append(t[2:])
            elif i + 1 < len(args):
                found.append(args[i + 1])
                i += 1
        i += 1
    return found


def _code_args(args: list, letters: str, stop: str = "") -> list:
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
            k = None
            for j, ch in enumerate(t[1:], 1):
                if ch in stop:
                    break  # an option whose attached value follows (perl -Mfeature)
                if ch in letters:
                    k = j
                    break
            if k is not None:
                if t[k + 1:]:
                    codes.append(t[k + 1:])
                elif i + 1 < len(args):
                    codes.append(args[i + 1])
                    i += 1
        i += 1
    return codes


def _runs_a_command(tokens: list) -> bool:
    """A package runner in the form that runs another command (npm exec, uv run, uvx ...)."""
    name = os.path.basename(tokens[0])
    return name in _RUNNERS and (not _RUNNERS[name] or tokens[1:2] and tokens[1] in _RUNNERS[name])


# Variables that make an interpreter, a shell or the dynamic linker load a file.
_LOADER_ENV_RE = re.compile(r"^(NODE_OPTIONS|PERL5OPT|RUBYOPT|PYTHONSTARTUP|BASH_ENV|ENV|LD_PRELOAD|"
                            r"DYLD_INSERT_LIBRARIES|LESSOPEN|LESSCLOSE)\+?=(.+)$", re.S)
# ENV is also an ordinary variable name: it counts with a shell as a program word on the line.
_SHELL_WORD_RE = re.compile(r"(?:^|[\s;&|(/'\"`])(?:sh|dash|ksh|ash|bash|zsh)(?=$|[\s;&|)'\"`])")
_DECLARERS = ("export", "declare", "typeset", "readonly", "local")


def _loader_env_matches(original: list, ctx: _Ctx, depth: int) -> list:
    """Code loaded through the environment, set as a command prefix, with export, or in the
    arguments of a wrapper. NODE_OPTIONS is read with node's loader-option rules; ENV counts
    when a shell is run on the same line; any other of these variables set
    to a value is held."""
    rest = _strip_prefix(list(original))
    words = original[:len(original) - len(rest)]
    if rest and (os.path.basename(rest[0]) in _DECLARERS or os.path.basename(rest[0]) in WRAPPERS
                 or _runs_a_command(rest)):
        words = original
    out: list = []
    for word in words:
        m = _LOADER_ENV_RE.match(word)
        if not m:
            continue
        held = {"id": "control-loader-env", "category": "control",
                "describe": "load code through the environment: %s" % _short(word)}
        value = m.group(2)
        if m.group(1) == "ENV" and not _SHELL_WORD_RE.search(ctx.full_text):
            continue  # an ordinary variable of that name
        if m.group(1) != "NODE_OPTIONS" or _expand(value) is None or "__dwsub" in value:
            out.append(held)
            continue
        try:
            options = shlex.split(value)
        except ValueError:
            out.append(held)
            continue
        for loader in _loader_args(options, "node"):
            out += _inline_matches(loader, ctx, depth)
    return out


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


def _input_is_unreadable_for(suffix: list, marks: list, ctx: _Ctx) -> bool:
    """Whether stdin text substituted into this command matters: in the program position, or
    anywhere in a sensitive program, a shell, an interpreter or a wrapper (where it may be
    code or decide the classification). For other programs it is plain data."""
    words = _strip_prefix(list(suffix))
    if not words:
        return False
    if any(mark in words[0] for mark in marks):
        return True
    name = os.path.basename(words[0])
    return name in sensitive_programs(ctx.rules) or name in SHELLS or name in WRAPPERS or \
        bool(_INTERPRETER_RE.match(name)) or name in _RUNNERS


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
    replaced = tokens
    marks: list = []
    if incomplete:  # text from standard input replaces these words
        marks = sorted(_placeholders(name, tokens), key=len, reverse=True)
        replaced = []
        for t in tokens:
            for mark in marks:
                t = t.replace(mark, "__dwsub_input__")
            replaced.append(t)
    inner_seg = seg
    sub.marks = tuple(marks) + tuple(ctx.marks)  # replace strings are run-time parts of paths
    first_operand = None
    for k in range(start, len(tokens)):
        if tokens[k].startswith("-") or re.search(r"\s", tokens[k]):
            continue  # an option or a command string (read below) is not a program name
        declared = marks and tokens[k - 1] in ("-I", "--replace")
        if marks and any(mark in tokens[k] for mark in marks):
            if declared or (first_operand is not None and first_operand < k):
                continue  # the replace string itself, or a later argument: data
        if first_operand is None and not declared:
            first_operand = k
        suffix = tokens[k:]
        if marks and _input_is_unreadable_for(suffix, marks, sub):
            suffix = replaced[k:]  # stdin text in a deciding or code position: run-time
        out += _analyze(suffix, [], inner_seg, sub.fork(), depth + 1, incomplete)
    for token in tokens[start:]:
        out += _string_matches(_command_strings(token), sub, depth)
    if incomplete and first_operand is not None and seg["pipe_in"] and \
            any(ctx.protected.words_name(words) for words in ctx.stdin_commands):
        # The words on standard input spell a protected path: do they land in a write position?
        inner = replaced[first_operand:]
        if not any("__dwsub_input__" in t for t in inner):
            inner = inner + ["__dwsub_input__"]  # no replace string: appended at the end
        if any("__dwsub_input__" in inner[i] for i in _write_positions(inner, sub, False)):
            out.append(_state_match(" ".join(tokens)))
    return out


def _shell_matches(text: str, ctx: _Ctx, depth: int = 0) -> list:
    if depth > 6:
        return [_unreadable_match()]
    try:
        lexed = _Lexer(text).run()
    except _Unreadable:
        return [_unreadable_match()]
    matches: list = []
    ctx.sub_bodies = lexed.subs
    start = ctx.fork()
    before = None
    for seg in lexed.segments:
        # Everything upstream in the same pipeline may put file names on standard input.
        upstream = list(ctx.stdin_commands) if seg["pipe_in"] else []
        if seg["pipe_in"] and before is not None:
            try:
                upstream.append(_strip_prefix(_tokens(before["words"])))
            except _Unreadable:
                pass
        ctx.stdin_commands = upstream
        before = seg
        matches += _segment_matches(seg, ctx, depth)
    for body in lexed.subs:
        matches += _shell_matches(body, start.fork(), depth + 1)
    return matches


# test, [ and [[ evaluate the operands of these as arithmetic, where an array subscript such as
# 'a[$(cmd)]' runs cmd even inside single quotes.
_TEST_PROGRAMS = ("test", "[", "[[")
_ARITHMETIC_TESTS = ("-eq", "-ne", "-lt", "-le", "-gt", "-ge", "-v")


def _arithmetic_subscript(tokens: list) -> bool:
    """Whether an operand of an arithmetic test (either side of -eq and the like, the word after
    -v) holds a subscript with a command in it. A plain substitution there is only a value: its
    body is classified on its own."""
    for i in range(1, len(tokens)):
        if tokens[i] not in _ARITHMETIC_TESTS:
            continue
        operands = tokens[i + 1:i + 2] + (tokens[i - 1:i] if tokens[i] != "-v" and i > 1 else [])
        if any("[" in t and ("$(" in t or "`" in t or "__dwsub" in t) for t in operands):
            return True
    return False


def _segment_matches(seg: dict, ctx: _Ctx, depth: int) -> list:
    try:
        original = _tokens(seg["words"])
        redirects = [_unquote(w) for w in seg["redirects"]]
        for word in seg["reads"]:  # an input redirect is a read
            redirects.remove(_unquote(word))
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
    matches += _loader_env_matches(original, ctx, depth)
    wrapped = False
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
        if name in _TEST_PROGRAMS and _arithmetic_subscript(tokens):
            matches.append(_unreadable_match())  # an arithmetic operand runs its substitutions
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
            family = _FAMILY_ALIASES.get(family, family)
            codes = _code_args(rest, _CODE_LETTERS.get(family, "ce"),
                               stop=_LOADER_LETTERS.get(family, ""))
            for loader in _loader_args(rest, family):
                if _expand(loader) is None or "__dwsub" in loader:
                    matches.append(_unreadable_match())  # code loaded from a run-time name
                else:
                    matches += _inline_matches(loader, ctx, depth)
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
            tokens, wrapped = [], True
            break
        if _runs_a_command(tokens):
            matches += _wrapper_matches(tokens, seg, ctx, depth, start=1 if not _RUNNERS[name] else 2)
            tokens, wrapped = [], True
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
        matches += _find_write_matches(tokens, ctx)
    matches += _control_matches(original, tokens, redirects, ctx, wrapped)
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


_FOUND = "found-by-find"  # stands for a file find passes to -exec, somewhere under a start path
MAX_FIND_STARTS = 8


def _find_exec_matches(tokens: list, ctx: _Ctx, depth: int) -> list:
    """Classify the commands that `find -exec/-execdir/-ok/-okdir` runs."""
    starts = []
    for t in tokens[1:]:
        if t.startswith("-") or t in ("(", "!", ")"):
            break
        starts.append(t)
    sub = ctx.fork()
    sub.marks = (_FOUND,) + tuple(ctx.marks)  # the found name is a run-time part of paths
    out = []
    i = 0
    while i < len(tokens):
        if tokens[i] in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            while j < len(tokens) and tokens[j] not in (";", "+"):
                j += 1
            for start in (starts or ["."])[:MAX_FIND_STARTS]:
                sample = start.rstrip("/") + "/" + _FOUND
                inner = [sample if t == "{}" else t for t in tokens[i + 1:j]]
                if inner:
                    out += _analyze(inner, [], _new_segment(False), sub.fork(), depth + 1)
            i = j
        i += 1
    return out


# The protected files find may come across below a start directory, as (directory, path in it).
_GIT_HOOK_NAMES = """applypatch-msg pre-applypatch post-applypatch pre-commit pre-merge-commit
prepare-commit-msg commit-msg post-commit pre-rebase post-checkout post-merge pre-push pre-receive
update proc-receive post-receive post-update reference-transaction push-to-checkout pre-auto-gc
post-rewrite sendemail-validate fsmonitor-watchman post-index-change""".split()
_FINDABLE = [(".git", "hooks/" + hook) for hook in _GIT_HOOK_NAMES] + \
    [(".git", "config"), (".git", "config.worktree"), (".git", "info/attributes")] + \
    [(name, f) for name, files in _PROTECTED_NAMES.items() for f in files or ()]


def _writes_what_it_finds(inner: list, ctx: _Ctx) -> bool:
    """Whether the command of a find -exec has {} in a write position."""
    if not inner or not any("{}" in t for t in inner):
        return False
    name = os.path.basename(inner[0])
    if name in WRAPPERS or name in SHELLS or name in _RUNNERS or _INTERPRETER_RE.match(name):
        return True  # what it does with the name is not modelled
    return any("{}" in inner[i] for i in _write_positions(inner, ctx, False))


def _may_hold_protected(start: str, ctx: _Ctx) -> bool:
    """Whether a start directory of find is, contains or lies inside a protected directory.
    A directory that cannot be looked at may."""
    real = None if _dynamic(start) else _resolve(start, ctx.cwd)
    if real is None or not os.path.isdir(real):
        return True
    low = real.lower()
    if any(part in _PROTECTED_NAMES for part in low.split("/")) or \
            any(os.path.lexists(os.path.join(real, name)) for name in _PROTECTED_NAMES):
        return True
    targets = list(ctx.protected.files) + ctx.protected.dirs
    return any(_inside(t, low) or _inside(low, t) for t in targets)


_FIND_NAME_TESTS = ("-name", "-iname")
_FIND_PATH_TESTS = ("-path", "-ipath", "-wholename", "-iwholename")
_FIND_OR = ("-o", "-or", ",")


def _find_chain_start(tokens: list, action: int, first: int) -> int:
    """Where the and-chain of tests that leads to the action at `action` begins: after the
    nearest -o before it that is not inside a parenthesis the chain closes."""
    depth = 0
    for i in range(action - 1, first - 1, -1):
        if tokens[i] == ")":
            depth += 1
        elif tokens[i] == "(":
            if depth == 0:
                return i + 1
            depth -= 1
        elif tokens[i] in _FIND_OR and depth == 0:
            return i + 1
    return first


def _find_pruned(tokens: list, i: int) -> bool:
    """Whether the -name or -path test at `i` is pruned, in one of the exact shapes
    `TEST PATTERN -prune` and `( TEST PATTERN -o TEST PATTERN ... ) -prune`. In any other
    shape the -prune is not taken to govern the test."""
    tests = _FIND_NAME_TESTS + _FIND_PATH_TESTS
    if tokens[i + 2:i + 3] == ["-prune"]:
        return True
    first = i
    while first >= 3 and tokens[first - 1] in ("-o", "-or") and tokens[first - 3] in tests:
        first -= 3
    last = i
    while tokens[last + 2:last + 3] in (["-o"], ["-or"]) and tokens[last + 3:last + 4] and \
            tokens[last + 3] in tests:
        last += 3
    return tokens[first - 1:first] == ["("] and tokens[last + 2:last + 4] == [")", "-prune"]


_FIND_EXEC = ("-exec", "-execdir", "-ok", "-okdir")
_FIND_DEPTH_FIRST = ("-delete", "-depth", "-d")  # -prune has no effect under any of these


def _find_own_words(tokens: list) -> list:
    """The words of a find command outside its -exec/-ok spans (`-exec ... ;` or `+`)."""
    own, i = [], 1
    while i < len(tokens):
        if tokens[i] in _FIND_EXEC:
            while i < len(tokens) and tokens[i] not in (";", "+"):
                i += 1
        else:
            own.append(tokens[i])
        i += 1
    return own


def _find_write_matches(tokens: list, ctx: _Ctx) -> list:
    """find that deletes, or hands to a writing command, files it finds by itself. For each
    such action the tests of its and-chain are read: positive -name and -path tests say what
    it may find, negated ones and pruned directories what it cannot (no directory counts as
    pruned when find goes depth-first: -delete, -depth or -d). Held when a protected
    file (_FINDABLE) is not ruled out, and either the tests ask for one outright (-name
    pre-push, -path '*/.git/*') or a start directory may hold protected files."""
    first = 1
    while first < len(tokens) and not (tokens[first].startswith("-") or tokens[first] in ("(", "!", ")")):
        first += 1
    starts = tokens[1:first] or ["."]
    pruned = [] if any(t in _FIND_DEPTH_FIRST for t in _find_own_words(tokens)) else \
        [(tokens[i], tokens[i + 1].lower()) for i in range(first, len(tokens) - 1)
         if tokens[i] in _FIND_NAME_TESTS + _FIND_PATH_TESTS and _find_pruned(tokens, i)]
    i = first
    while i < len(tokens):
        t = tokens[i]
        end = i
        if t in _FIND_EXEC:
            while end < len(tokens) and tokens[end] not in (";", "+"):
                end += 1
            writes = _writes_what_it_finds(tokens[i + 1:end], ctx)
        else:
            writes = t == "-delete"
        if writes and _find_may_reach_protected(tokens, _find_chain_start(tokens, i, first), i,
                                                pruned, starts, ctx):
            return [_state_match(" ".join(tokens))]
        i = end + 1
    return []


def _find_may_reach_protected(tokens: list, begin: int, action: int, pruned: list, starts: list,
                              ctx: _Ctx) -> bool:
    names, paths, negated = [], [], []
    for k in range(begin, action - 1):
        t = tokens[k]
        if t not in _FIND_NAME_TESTS + _FIND_PATH_TESTS:
            continue
        test = (t, tokens[k + 1].lower())
        if test in pruned:
            continue
        if tokens[k - 1] in ("!", "-not"):
            negated.append(test)
        else:
            (names if t in _FIND_NAME_TESTS else paths).append(test[1])

    def matches(test, directory, inside, as_directory=False) -> bool:
        kind, pattern = test
        where = directory if as_directory else directory + "/" + inside
        if kind in _FIND_NAME_TESTS:
            return _may_equal(pattern, os.path.basename(where))
        return _may_equal(pattern, "./" + where) or _may_equal(pattern, "./x/" + where)

    asked = any(n == os.path.basename(inside) for n in names for _d, inside in _FINDABLE) or \
        any(re.search(re.escape(name) + r"(?![a-z0-9_-])", q) for q in paths
            for name in _PROTECTED_NAMES)
    if not asked and not any(_may_hold_protected(start, ctx) for start in starts):
        return False
    for directory, inside in _FINDABLE:
        if any(matches(test, directory, inside) for test in negated) or \
                any(matches(test, directory, inside, as_directory=True) for test in pruned):
            continue  # ruled out
        if (not names or any(matches(("-name", n), directory, inside) for n in names)) and \
                (not paths or any(matches(("-path", q), directory, inside) for q in paths)):
            return True
    return False


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


# -- write positions --------------------------------------------------------------
#
# Every word of a command is a write position, with two shortcuts. Both apply only when the
# program word is a bare name (./cat need not be cat) and every option on the line is one
# the program's entry accounts for; otherwise every word is checked.
#   read-only programs: no word is a write position;
#   cp and rsync: only the last operand (the destination) and the options are.

# Plain flags of cp and rsync: none takes a separate value, none names a file to write.
_COPY_FLAGS = {
    "cp": re.compile(r"-[aAbcdfHiLnpPrRTuvxX]+|--(archive|recursive|force|interactive|"
                     r"no-clobber|preserve(=.*)?|no-preserve=.*|verbose|update|dereference|"
                     r"no-dereference|parents)"),  # not -l or -s: a link to the source
    "rsync": re.compile(r"-[aAvzrhPnqtlpgoDuHXEcixWSO]+|--(archive|recursive|verbose|compress|"
                        r"human-readable|progress|stats|dry-run|quiet|checksum|update|links|"
                        r"times|perms|itemize-changes|mkpath|relative|partial|info=.*|"
                        r"delete(-after|-before|-during|-excluded|-delay)?|"
                        r"(exclude|include)=.*)"),
}
# git subcommands that read or stage the working tree: their path arguments are not written.
# (Of git stash, only list and show.)
_GIT_READS = {"add", "diff", "status", "log", "show", "blame", "ls-files", "grep", "cat-file"}
_GIT_WRITE_OPTIONS = ("--output", "--open-files-in-pager", "--ext-diff", "--textconv")
# Per program, the options whose value is a pattern to match names with, not a file.
_EXCLUDES = ("--exclude", "--include")
_PATTERN_OPTIONS = {"find": ("-name", "-iname", "-path", "-ipath", "-wholename"),
                    "rsync": _EXCLUDES, "tar": _EXCLUDES, "zip": _EXCLUDES,
                    "grep": _EXCLUDES + ("--exclude-dir",),
                    "rg": _EXCLUDES + ("--exclude-dir", "-g", "--glob")}


def _git_option_writes(arg: str) -> bool:
    """An option that makes a reading git subcommand write a file or run a program; git
    accepts any unambiguous prefix of a long option."""
    name = arg.split("=", 1)[0]
    if arg.startswith("-O"):
        return True
    return len(name) > 3 and any(o.startswith(name) or name.startswith(o) for o in _GIT_WRITE_OPTIONS)


def _write_positions(tokens: list, ctx: _Ctx, incomplete: Optional[bool] = None) -> list:
    """Indexes of the words of one command that may name a file it writes."""
    incomplete = ctx.incomplete if incomplete is None else incomplete
    found = list(range(len(tokens)))
    name = tokens[0]  # only a bare name is the program it is called after
    options = [t for t in tokens[1:] if _is_option(t)]
    entry = _READ_ONLY.get(name)
    if entry is not None:
        short, long, most, check = entry
        operands = len(tokens) - 1 - len(options)
        if all((long if t.startswith("--") else short).fullmatch(t) for t in options) and \
                (most is None or operands <= most) and (check is None or check(tokens)):
            return []
    elif name in _COPY_FLAGS and not incomplete:
        end = tokens.index("--") if "--" in tokens else len(tokens)
        operands = [i for i in range(1, len(tokens)) if i != end
                    and not (i < end and _is_option(tokens[i]))]
        if len(operands) >= 2 and all(_COPY_FLAGS[name].fullmatch(t) for t in tokens[1:end]
                                      if _is_option(t)):
            found = [i for i in found if i not in operands[:-1]]
    elif name == "git":
        sub, args, _repo, unreadable = _git_parts(tokens, ctx)
        staged = any(a == "--staged" or re.fullmatch(r"-[A-Za-z]*S[A-Za-z]*", a) for a in args)
        worktree = any(a == "--worktree" or re.fullmatch(r"-[A-Za-z]*W[A-Za-z]*", a) for a in args)
        reads = sub in _GIT_READS or (sub == "stash" and args[:1] in (["list"], ["show"])) or \
            (sub == "restore" and staged and not worktree)
        if reads and not unreadable and not any(_git_option_writes(a) for a in args):
            found = found[:len(tokens) - len(args) - 1]  # git's own options before the subcommand
    # The value of one of the program's pattern options is not a write position.
    patterns = _PATTERN_OPTIONS.get(name, ())
    skip = {i + 1 for i in found if tokens[i] in patterns}
    skip |= {i for i in found if tokens[i].split("=", 1)[0] in patterns and "=" in tokens[i]}
    return [i for i in found if i not in skip]


MAX_LOOP_WORDS = 64


def _loop_words(original: list, ctx: _Ctx) -> bool:
    """For `for NAME in WORDS`, `select NAME in WORDS` and `case WORD in`: remember the words
    a loop variable stands for. They are data until a write position uses the variable."""
    words = [t for t in original if not _ASSIGNMENT_RE.match(t)]
    if words[:1] == ["case"]:
        return True
    if words[:1] not in (["for"], ["select"]) or len(words) < 2:
        return False
    values = words[3:] if words[2:3] == ["in"] else []
    ctx.loop_words[words[1]] = values if len(values) <= MAX_LOOP_WORDS else None  # None: not read
    return True


def _read_words(tokens: list, ctx: _Ctx) -> None:
    """`... | while read NAME`: the variable stands for what the upstream commands print. When
    their words spell a protected path, those words are its values."""
    if tokens[:1] != ["read"]:
        return
    named = [w for words in ctx.stdin_commands if ctx.protected.words_name(words) for w in words[1:]]
    for name in tokens[1:]:
        if not name.startswith("-") and named:
            ctx.loop_words[name] = named if len(named) <= MAX_LOOP_WORDS else None


def _loop_variants(word: str, ctx: _Ctx) -> Optional[list]:
    """A word, and the word with each value of a loop variable it uses put in. None when it
    uses a variable whose list is too long to read."""
    out = [word]
    for name, values in ctx.loop_words.items():
        rx = re.compile(r"\$\{%s\}|\$%s(?![A-Za-z0-9_])" % (re.escape(name), re.escape(name)))
        if rx.search(word):
            if values is None:
                return None
            out += [rx.sub(lambda m: value, word) for value in values]
    return out


def _control_matches(original: list, tokens: list, redirects: list, ctx: _Ctx,
                     wrapped: bool = False) -> list:
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
    # Write positions. Redirect targets always are. Of the words: for a wrapper, its own
    # leading words and options (every suffix of its arguments was classified as a command of
    # its own, with that command's write positions); otherwise see _write_positions.
    head = len(original) - len(tokens)
    _read_words(tokens, ctx)
    if wrapped:
        own = len(original) - len(_strip_prefix(list(original)))
        checked = [i for i, t in enumerate(original)
                   if i <= own or t.startswith("-") or re.search(r"\s", t)]
    elif tokens and original[head:] == tokens:
        positions = _write_positions(tokens, ctx)
        checked = [head + i for i in positions]
        if positions:
            checked = list(range(head)) + checked
    elif _loop_words(original, ctx):
        checked = []  # data here; checked where the loop's body writes the variable
    else:
        checked = list(range(len(original)))
    if tokens and os.path.basename(tokens[0]) == "rg" and any(re.match(r"--pre(-glob)?(=|$)", t) for t in tokens[1:]):
        out.append(_unreadable_match())  # rg runs the --pre command on every file it reads
    words = [original[i] for i in checked if i != skip] + list(redirects)
    variants = [_loop_variants(w, ctx) for w in words]
    if None in variants:  # a write position uses a loop variable whose list was too long to read
        out.append(_unreadable_match())
    words = [variant for found in variants for variant in found or ()]
    if any(ctx.protected.token_hit(w, ctx.cwd, ctx.sub_bodies, ctx.marks) for w in words):
        out.append(_state_match(" ".join(original)))
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
    names |= {"python", "python3", "pypy", "perl", "ruby", "node", "nodejs", "php", "deno", "bun",
              "tsx", "ts-node"}
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
    if host in _LOCAL_HOSTS or (host.endswith(".localhost") and host != ".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
    # A field or input option in any spelling, or a method other than GET, makes it a write.
    # A long option counts under any prefix of its name (an ambiguous prefix fails closed).
    for i, t in enumerate(tokens):
        following = tokens[i + 1] if i + 1 < len(tokens) else ""
        if t.startswith("--") and len(t) > 2:
            name, eq, val = t.partition("=")
            if any(o.startswith(name) for o in ("--field", "--raw-field", "--input")):
                return True
            if "--method".startswith(name) and (val if eq else following).upper() != "GET":
                return True
        elif t.startswith("-") and not t.startswith("--"):
            for k, ch in enumerate(t[1:], 1):  # a cluster of short options, as gh reads it
                if ch in "fF":
                    return True
                if ch == "X" and (t[k + 1:] or following).upper() != "GET":
                    return True
                if ch in "XHqtp":  # these take a value: the rest of the word is that value
                    break
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


def _registered_project_at(cwd: str, registry: dict) -> Optional[dict]:
    """The registered project whose path holds realpath(cwd) most closely, or None."""
    real = os.path.realpath(cwd)
    projects = [p for p in registry.get("projects", []) if p.get("path") and _inside(real, p["path"])]
    return max(projects, key=lambda p: len(p["path"])) if projects else None


def _refuse_for_ended_run(run_id: str, tool: str, tool_input: dict, cwd: str) -> Optional[dict]:
    """`DW_RUN_ID` names a run that is not running or blocked (or no run at all) and no other
    run is active here: a call that matches a rule is refused outright. No dialog is opened
    and no record is changed; any other call is allowed."""
    registry = store.load_registry()
    try:
        run = store.load_run(run_id)
    except store.RunNotFound:
        run = None
    if run is not None:
        project, state = _project_for(run, registry), str(run.get("state") or "unknown")
        rules = load_rules(project) + [run_context(run_id)]  # its own result note stays writable
    else:
        project, state = _registered_project_at(cwd, registry), "unknown"
        rules = load_rules(project or {})
    match = classify(tool, tool_input, cwd, (project or {}).get("path") or cwd, rules)
    return None if match is None else _inactive_output(run_id, state)


def _probably_inside_run(cwd) -> bool:
    """After an error: whether the call may belong to a run. A session started by `dw run`
    carries `DW_RUN_ID` whatever its run's state now is, so that alone counts. Never raises."""
    try:
        if os.environ.get("DW_RUN_ID"):
            return True
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
        return False


# -- the hook ------------------------------------------------------------------------


def _output(decision: str, reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": decision,
                                   "permissionDecisionReason": reason}}


def _inactive_output(run_id: str, state: str) -> dict:
    return _output("deny", INACTIVE_REASON % (run_id, state))


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
            outcome["state"] = str(r.get("state") or "unknown")
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
    if kind == "gone":  # the run ended after it was found: refused, as for any ended run
        return _inactive_output(run_id, outcome["state"])
    if kind in ("approved", "granted"):
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
        # One line: AGTerm refuses control characters, and agterm sanitises the rest.
        message = "%s \u2014 %s: %s" % (describe, tool, _action_text(tool, tool_input))
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
            # The terminal's own error text is never relayed to the agent (it is in dw.log);
            # only an unreachable AGTerm or a guard failure is reported as a guard error.
            relayable = error is not None and (isinstance(error, agterm.AgtermUnavailable) or
                                               not isinstance(error, agterm.AgtermError))
            if relayable:
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
        run_id = os.environ.get("DW_RUN_ID")
        return _refuse_for_ended_run(run_id, tool, tool_input, cwd) if run_id else None
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
    """True when a `PreToolUse` hook command in the settings file runs `dw guard` for every
    tool (its group's matcher is absent, empty or `*`)."""
    return guard_entry_argv(settings_path) is not None


def guard_entry_narrow(settings_path: Path) -> bool:
    """True when the settings file runs `dw guard` only in groups whose matcher leaves some
    tools out."""
    return not guard_entry_present(settings_path) and bool(_guard_entries(settings_path))


def covers_all_tools(group: dict) -> bool:
    """Whether a `PreToolUse` hook group runs for every tool."""
    return group.get("matcher") in (None, "", "*")


def guard_entry_argv(settings_path: Path) -> Optional[list]:
    """The argv (`[path to dw, "guard"]`) of the first `PreToolUse` hook command in the
    settings file that runs `dw guard` for every tool, or None."""
    return next((argv for group, argv in _guard_entries(settings_path)
                 if covers_all_tools(group)), None)


def _guard_entries(settings_path: Path) -> list:
    """(group, argv) for every `PreToolUse` hook command in the settings file that runs
    `dw guard`, whatever its group's matcher."""
    try:
        with open(str(settings_path)) as fh:
            data = json.load(fh)
        groups = data["hooks"]["PreToolUse"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    if not isinstance(groups, list):
        return []
    found = []
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
                found.append((group, argv))
    return found
