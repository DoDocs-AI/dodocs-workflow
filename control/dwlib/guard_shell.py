"""Shell side of the approval guard: lexing commands into segments, quoting, brace and
path expansion, and the lists of wrappers and interpreters. The rule for what the parser
cannot read is in guard.py's module docstring."""
from __future__ import annotations

import fnmatch
import glob
import os
import re
import shlex
import time
from typing import Optional
UNREADABLE = "command cannot be read"


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


# -- shell lexing ----------------------------------------------------------


class _Unreadable(Exception):
    pass


def _new_segment(pipe_in: bool) -> dict:
    # before/after: the operator that ends the previous segment and this one ("" at either
    # end of the text; ";", "\n", "&&", "||", "|", "&", "(" or ")"); depth: how many
    # parentheses it is inside.
    return {"words": [], "redirects": [], "reads": [], "heredocs": [], "pipe_in": pipe_in,
            "pipe_out": False, "keep": False, "before": "", "after": "", "depth": 0}


def _scan_body(target: "_Lexer", body: str) -> None:
    """Add to `target` the command substitutions ($( ) and backticks) of an unquoted
    here-document body or an arithmetic expansion, read as a double-quoted word is (see
    _Lexer.read_double) except that a double quote is plain text: a backslash escapes the next
    character, and $(( is read both ways (see _Lexer.double_paren)."""
    if "$" not in body and "`" not in body:
        return
    lexer = _Lexer(body)
    while lexer.i < lexer.n:
        c = body[lexer.i]
        if c == "\\":
            lexer.i += 2
        elif body.startswith("$((", lexer.i):
            lexer.i = lexer.double_paren(lexer.i)
        elif body.startswith("$(", lexer.i):
            lexer.substitution(lexer.i + 2)
        elif c == "`":
            lexer.backtick()
        else:
            lexer.i += 1
    target.subs += lexer.subs
    target.alt_subs += lexer.alt_subs


# Every redirection operator of bash and zsh, longest first, after an optional fd number or
# `&`: zsh's clobber overrides (>!, >>!, >&!, &>!, ...) included, so their targets are read as
# targets (and checked as write positions) whether or not a space follows the operator.
_REDIRECT_RE = re.compile(
    r"(\d*)(&>>\||&>>!|>>&\||>>&!|&>>|>>&|&>\||&>!|>&\||>&!|>>\||>>!|&>|>&|>>|>\||>!|"
    r"<<<|<<-|<<|<&|<>|>|<)")


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
        # Bodies that are command substitutions only under one reading of `$((` (a
        # substitution starting with a subshell); classified as such too (guard._shell_matches).
        self.alt_subs: list = []
        self.seg = _new_segment(False)
        self.pending: list = []
        # False once the text uses anything but simple commands joined by &&, ||, ;, newlines
        # or pipes (which the segments record): a background `&`, a subshell or group
        # parenthesis (a function definition `name()` included) or a process substitution.
        self.flat = True
        self.depth = 0  # parentheses open at the current position

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
                self.end(op="\n")
                self.i += 1
                self.heredoc_bodies()
            elif c == ";":
                self.end(op=";")
                self.i += 1
            elif c == "&" and nxt == "&":
                self.end(op="&&")
                self.i += 2
            elif c == "&" and nxt == ">":
                self.redirect()
            elif c == "&":
                self.flat = False
                self.end(op="&")
                self.i += 1
            elif c == "|":
                if nxt == "|":
                    self.end(op="||")
                    self.i += 2
                else:
                    self.end(pipe=True, op="|")
                    self.i += 2 if nxt == "&" else 1
            elif c in "<>" and nxt == "(":
                self.flat = False
                self.seg["words"].append(self.substitution(self.i + 2))
            elif c in "()":
                self.flat = False
                self.depth += 1 if c == "(" else -1
                self.end(op=c)
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
            for _delim, _strip, seg, _quoted in self.pending:
                seg["heredocs"].append("")
        return self

    def end(self, pipe: bool = False, op: str = "") -> None:
        seg = self.seg
        seg["pipe_out"] = pipe
        seg["after"] = op
        if seg["words"] or seg["redirects"] or seg["heredocs"] or seg["keep"]:
            self.segments.append(seg)
            self.seg = _new_segment(pipe)
            self.seg["before"] = op
        else:  # an empty segment: the next one follows the operator before it, and this one
            before = seg["before"] if op in (";", "\n") and seg["before"] not in ("", ";", "\n") \
                else op
            self.seg = _new_segment(pipe)
            self.seg["before"] = before
        self.seg["depth"] = self.depth

    def read_heredoc(self, j: int, delim: str, strip: bool, quoted: bool) -> tuple:
        """(body, index after it) of a here-document whose body starts at `j`. The one reader
        for every place a body is skipped or kept: `<<-` strips leading tabs, and with an
        unquoted delimiter each backslash-newline pair is deleted (an odd number of trailing
        backslashes joins the next line) before the delimiter is looked for."""
        s, lines = self.s, []
        while j < self.n:
            k = s.find("\n", j)
            line = s[j:] if k < 0 else s[j:k]
            j = self.n if k < 0 else k + 1
            while not quoted and j < self.n and (len(line) - len(line.rstrip("\\"))) % 2 == 1:
                k = s.find("\n", j)
                line = line[:-1] + (s[j:] if k < 0 else s[j:k])
                j = self.n if k < 0 else k + 1
            if (line.lstrip("\t") if strip else line) == delim:
                break
            lines.append(line)
        return "\n".join(lines), j

    def heredoc_bodies(self) -> None:
        for delim, strip, seg, quoted in self.pending:
            body, self.i = self.read_heredoc(self.i, delim, strip, quoted)
            seg["heredocs"].append(body)
            if not quoted:
                _scan_body(self, body)
        self.pending = []

    def redirect(self) -> None:
        m = _REDIRECT_RE.match(self.s, self.i)
        if not m:
            raise _Unreadable("redirection")
        op = m.group(2)
        self.i = m.end()
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
            # A quoted delimiter (any quote or backslash in it) makes the body literal text;
            # otherwise the shell runs the body's substitutions, as in a double-quoted word.
            quoted = any(c in word for c in "'\"\\")
            self.pending.append((delim, op == "<<-", self.seg, quoted))
        elif op == "<<<":
            self.seg["heredocs"].append(_unquote(word))
        elif op in (">&", "<&") and re.fullmatch(r"\d+-?|-", word):
            return
        else:
            self.seg["redirects"].append(word)
            if op == "<":  # the only operator that cannot write its target
                self.seg["reads"].append(word)

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
                j = self.double_paren(self.i)
                out.append(s[self.i:j])
                self.i = j
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
                j = self.double_paren(self.i)
                out.append(s[self.i:j])
                self.i = j
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
                for delim, strip, quoted in heredocs:
                    _body, j = self.read_heredoc(j, delim, strip, quoted)
                heredocs = []
                continue
            if c == "<" and s.startswith("<<", j) and not s.startswith("<<<", j):
                m = re.match(r"<<(-?)[ \t]*(\\?)(['\"]?)([A-Za-z0-9_.-]+)\3", s[j:])
                if m:
                    heredocs.append((m.group(4), m.group(1) == "-", bool(m.group(2) or m.group(3))))
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

    def arithmetic(self, start: int, close: int) -> None:
        """An arithmetic expansion $(( ... )) between `start` and the closing `))` at `close`:
        its command substitutions are classified like any other; a subscript holding one (the
        shell evaluates it) cannot be read."""
        text = self.s[start:close - 1]
        if "$(" not in text and "`" not in text:
            return
        if "[" in text:
            raise _Unreadable("a command substitution inside an arithmetic subscript")
        _scan_body(self, text)

    def double_paren(self, i: int) -> int:
        """`$((` at `i` is read both ways, as the shell may: as arithmetic (see `arithmetic`)
        and as a command substitution whose body starts with a subshell (`alt_subs`). Returns
        the index after it."""
        try:
            arith = self.close_paren(i + 3, 2)
        except _Unreadable:
            arith = None
        try:
            command = self.close_paren(i + 2)
        except _Unreadable:
            command = None
        if arith is None and command is None:
            raise _Unreadable("unterminated $((")
        if arith is not None:
            self.arithmetic(i + 3, arith)
        if command is not None:
            self.alt_subs.append(self.s[i + 2:command])
        return (command if command is not None else arith) + 1

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
                             r"deno|bun|tsx|ts-node|lua[0-9.]*|luajit|Rscript|julia|tclsh|wish|pwsh|powershell|"
                             r"groovy|elixir|erl|escript|swift|expect)$")
_KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!", "{", "}",
             "coproc"}
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")


# A command the guard cannot read: its own category, approvable like any other but never
# when the same call also matches another category. The rule id keeps its old name so that
# existing run records stay valid.
UNREADABLE_ID = "control-unreadable"
_UNREADABLE_RULE = {"id": UNREADABLE_ID, "category": "unreadable", "describe": UNREADABLE,
                    "tool": "Bash"}


def _unreadable_match() -> dict:
    return {"id": UNREADABLE_ID, "category": "unreadable", "describe": UNREADABLE}


# What cannot be read, where the control point's own protection may depend on it: the text
# names the control point, what cannot be read is a write position or a git override, or it
# is shell or interpreter code that could not be scanned at all. Held as `control`.
UNREADABLE_STATE_ID = "control-unreadable-state"
UNREADABLE_STATE = "command cannot be read and may change the control point"


def _unreadable_state_match() -> dict:
    return {"id": UNREADABLE_STATE_ID, "category": "control", "describe": UNREADABLE_STATE}


def _is_unreadable(match: dict) -> bool:
    return match.get("id") in (UNREADABLE_ID, UNREADABLE_STATE_ID)


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


# zsh precommand modifiers that run the words after them as the command.
_ZSH_PRECOMMANDS = {"noglob", "nocorrect", "-"}


def _strip_prefix(tokens: list) -> list:
    while tokens:
        t = tokens[0]
        if t in ("for", "case", "select"):
            return []
        if t in _KEYWORDS or t.endswith("()") or t in _ZSH_PRECOMMANDS:
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
            "dtruss", "valgrind", "entr", "nodemon",
            # zsh `repeat COUNT command`: as a wrapper every later word is read as a possible
            # command start, so an unusual count word (1+2, "3", $((2)), x) hides nothing.
            "repeat"}
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
_EXACT_VARIABLE_RE = re.compile(r"\s*\$\{?\w+\}?\s*")


def _run_time_text(token: str) -> bool:
    """An argument whose whole text is only known at run time."""
    return "__dwsub" in token or bool(_EXACT_VARIABLE_RE.fullmatch(token))


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _word_dynamic(word: str) -> bool:
    """A word whose value is only known when the command runs, or a pattern."""
    if word in ("[", "[[", "{", "}", "{}"):
        return False
    return _expand(word) is None or any(ch in word for ch in "*?[{")


# -- idioms read in full: a static variable, a small function, set earlier in the same command

# A value that means the same written out as substituted: no quote, expansion, glob, brace,
# tilde, or shell syntax; spaces only split words.
_STATIC_VALUE_RE = re.compile(r"[A-Za-z0-9_./:@%+,=-]+( [A-Za-z0-9_./:@%+,=-]+)*")
# What a value's first word must look like when the variable is used as the program.
_PROGRAM_NAME_RE = re.compile(r"[A-Za-z0-9_./][A-Za-z0-9_./+-]*")
# Words that can change what a name means (or how a value splits) somewhere in a command; any
# of them anywhere in it (`.` only as a command) and no name is resolved.
_REDEFINING_WORDS = {"eval", "source", "declare", "typeset", "local", "readonly", "export",
                     "unset", "read", "mapfile", "readarray", "getopts", "let", "set", "setopt",
                     "unsetopt", "shopt", "emulate", "alias", "unalias", "trap", "enable",
                     "builtin"}


def _shell_word_lists(lexed: "_Lexer", depth: int = 0) -> Optional[list]:
    """The words (quotes removed) of every simple command of a lexed text and of every
    substitution body in it, one list per command; None when a part cannot be read."""
    out: list = []
    try:
        for seg in lexed.segments:
            out.append(_tokens(seg["words"]))
    except _Unreadable:
        return None
    for body in list(lexed.subs) + list(lexed.alt_subs):
        if depth > 6:
            return None
        try:
            inner = _Lexer(body).run()
        except _Unreadable:
            if body in lexed.alt_subs:
                continue  # read as arithmetic only
            return None
        words = _shell_word_lists(inner, depth + 1)
        if words is None:
            return None
        out += words
    return out


def _names_may_change(word_lists: Optional[list]) -> bool:
    """Whether anything in the command could change what a variable or function name means:
    a redefining builtin (`eval`, `declare`, `read`, `unset`, `source`, `.` as a command ...),
    `printf -v`, or IFS anywhere. Unknown (None) counts as yes."""
    if word_lists is None:
        return True
    for words in word_lists:
        if any(w in _REDEFINING_WORDS or "IFS" in w for w in words):
            return True
        rest = [w for w in words if not _ASSIGNMENT_RE.match(w)]
        while rest and rest[0] in _KEYWORDS | {"then", "do", "else", "elif"}:
            rest = rest[1:]
        if rest[:1] == ["."]:
            return True
        if rest[:1] == ["printf"] and any(w.startswith("-v") for w in rest[1:]):
            return True
    return False
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_FUNCTION_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_COMPOUND_OPEN = {"if", "while", "until", "for", "select", "case", "{"}
_COMPOUND_CLOSE = {"fi", "done", "esac", "}"}
_STATEMENT_START = ("", ";", "\n")


def _compound_balance(words: list) -> int:
    """How many compound commands (if, loops, case, groups) the leading keywords of a segment
    open, minus how many they close."""
    balance = 0
    for w in words:
        if w in _COMPOUND_OPEN:
            balance += 1
        elif w in _COMPOUND_CLOSE:
            balance -= 1
        elif w not in _KEYWORDS and w not in ("then", "do", "else", "elif"):
            break
    return balance


def _static_value(raw: str) -> Optional[str]:
    """The value of an assignment's raw text when it is one literal: quotes allowed, nothing the
    shell would expand, and nothing that would read differently once substituted."""
    if not raw or re.search(r"[$`\\]|__dwsub", raw):
        return None
    try:
        parts = shlex.split(raw)
    except ValueError:
        return None
    if len(parts) != 1 or not _STATIC_VALUE_RE.fullmatch(parts[0]) or not parts[0].strip():
        return None
    words = parts[0].split()
    if any(_ASSIGNMENT_RE.match(w) or w in _KEYWORDS or w in _COMPOUND_OPEN or
           w in _COMPOUND_CLOSE or w in ("function", "[[", "]]") for w in words):
        return None
    return parts[0]


def _static_variables(text: str, segments: list, word_lists: Optional[list] = None) -> dict:
    """{name: value} for the variables the command assigns once, at top level, to a literal,
    before any use, and does nothing else with: every other mention of the name in the whole
    text is `$NAME` (not followed by `[`) or `${NAME}`, after the assignment. A top-level
    assignment is a segment of assignments only, outside any parenthesis or compound command,
    starting a statement (after nothing, `;` or a newline), not piped, not in the background.
    Read on the words with quotes removed too (`word_lists`): nothing may redefine names
    (`_names_may_change`), the name is never a word of its own, and exactly one word assigns it."""
    if _names_may_change(word_lists):
        return {}
    found: dict = {}
    depth = 0
    for seg in segments:
        words = seg["words"]
        top = seg["depth"] == 0 and depth == 0 and seg["before"] in _STATEMENT_START and \
            seg["after"] in ("", ";", "\n", "&&", "||") and not seg["pipe_in"] and \
            not seg["pipe_out"] and not seg["redirects"] and not seg["heredocs"] and \
            not seg["keep"]
        pairs = [re.match(r"^(%s)=(.*)$" % _NAME, w, re.S) for w in words]
        if words and all(pairs):
            for m in pairs:
                value = _static_value(m.group(2)) if top else None
                found.setdefault(m.group(1), []).append(value)
        depth += _compound_balance(words)
    out: dict = {}
    for name, values in found.items():
        if len(values) != 1 or values[0] is None:
            continue
        mentions = list(re.finditer(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % name, text))
        assigned = [m for m in mentions if text.startswith("=", m.end())]
        if len(assigned) != 1:
            continue
        words = [w for ws in word_lists for w in ws]
        if name in words or \
                sum(1 for w in words if re.match(r"^%s\+?=" % name, w)) != 1:
            continue
        at = assigned[0].start()
        ok = True
        for m in mentions:
            if m is assigned[0]:
                continue
            s, e = m.start(), m.end()
            plain = text[s - 1:s] == "$" and text[s - 2:s] != "$$" and text[e:e + 1] != "["
            braced = text[s - 2:s] == "${" and text[e:e + 1] == "}"
            if not (plain or braced) or s < at:
                ok = False
                break
        if ok:
            out[name] = values[0]
    return out


def _substitute_word(raw: str, variables: dict, split: bool) -> str:
    """A raw word with each unquoted or double-quoted `$NAME`/`${NAME}` of a static variable
    replaced by its value. Unquoted, the value splits into words where it has spaces (when
    `split`; otherwise it is put in double quotes); single-quoted text is left alone."""
    out: list = []
    i, quote = 0, None
    while i < len(raw):
        c = raw[i]
        if quote == "'":
            out.append(c)
            quote = None if c == "'" else quote
            i += 1
            continue
        if c == "\\":
            out.append(raw[i:i + 2])
            i += 2
            continue
        if c == "'" and quote is None:
            quote = "'"
        elif c == '"':
            quote = None if quote == '"' else '"'
        elif c == "$":
            m = re.match(r"\$(?:\{(%s)\}|(%s)(?![A-Za-z0-9_\[]))" % (_NAME, _NAME), raw[i:])
            name = m and (m.group(1) or m.group(2))
            if name in variables:
                value = variables[name]
                out.append(value if quote == '"' or split else '"%s"' % value)
                i += m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _split_unquoted(raw: str) -> list:
    """A raw word split at its unquoted spaces and tabs."""
    words, cur = [], []
    i, quote = 0, None
    while i < len(raw):
        c = raw[i]
        if quote:
            cur.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(raw):
                cur.append(raw[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c == "\\":
            cur.append(raw[i:i + 2])
            i += 1
        elif c in "'\"":
            quote = c
            cur.append(c)
        elif c in " \t":
            if cur:
                words.append("".join(cur))
                cur = []
        else:
            cur.append(c)
        i += 1
    if cur:
        words.append("".join(cur))
    return words


def _substituted_segment(seg: dict, variables: dict) -> dict:
    """The segment with its static variables substituted (see `_substitute_word`). Assignment
    words and redirect targets are not split."""
    if not variables:
        return seg
    lead = next((w for w in seg["words"] if not _ASSIGNMENT_RE.match(w)), None)
    words: list = []
    for w in seg["words"]:
        if _ASSIGNMENT_RE.match(w):
            words.append(_substitute_word(w, variables, False))
        else:
            words += _split_unquoted(_substitute_word(w, variables, True))
    program = next((w for w in words if not _ASSIGNMENT_RE.match(w)), None)
    if lead is not None and lead != program and \
            not (program and _PROGRAM_NAME_RE.fullmatch(re.sub(r"[\"']", "", program))):
        return seg  # a value in the program position that is no ordinary program name
    return {**seg, "words": words,
            "redirects": [_substitute_word(w, variables, False) for w in seg["redirects"]],
            "reads": [_substitute_word(w, variables, False) for w in seg["reads"]]}


_POSITIONAL_RE = re.compile(r'"\$([1-9])"|\$([1-9])|"\$\{([1-9])\}"|\$\{([1-9])\}')


def _function_plan(text: str, segments: list, word_lists: Optional[list] = None) -> tuple:
    """For small functions defined and called in the same command: ({segment index: segment
    to classify in its place}, {segment indexes not to classify}). A function counts when it is
    defined once, at top level (`name(){ ...; }`, `name() { ...; }`, `function name { ...; }`,
    `function name() { ...; }`), its body is one simple command (no pipe, redirect, here-document,
    substitution, or `$` other than whole-word "$@", $@, "$1".."$9", $1..$9) whose program is
    not a function the command defines, and every mention of its name in the whole text is the
    definition or a later top-level call (`name args...`). Each call is replaced by the body
    with the call's words substituted, keeping the call's redirects and pipes; a call whose
    result runs a function the command defines, or whose static argument would split or glob
    where the body leaves it unquoted, is unreadable (None). The definition itself is not
    classified. Any other function's body is classified where it is defined, and each of its
    plain calls (`name ...` as a command) is unreadable (None) as well as read by its words:
    what it runs was not read. Nothing in the command may redefine names
    (`_names_may_change`), and the name is a word (quotes removed) only at the definition and
    the calls."""
    blocked = _names_may_change(word_lists)
    every = [w for ws in word_lists for w in ws] if word_lists else []
    attempts: dict = {}  # name -> number of definitions, readable or not
    defined: dict = {}  # name -> (first index, last index, body words)
    depth = 0
    i = 0
    while i < len(segments):
        seg = segments[i]
        words = seg["words"]
        top = seg["depth"] == 0 and depth == 0 and seg["before"] in _STATEMENT_START
        name = body_at = None
        body: list = []
        if len(words) == 1 and seg["after"] == "(":
            name, body_at = words[0], i + 1
        elif len(words) == 2 and words[0] == "function" and seg["after"] == "(":
            name, body_at = words[1], i + 1
        elif len(words) >= 2 and words[0] == "function":
            name, body_at = words[1], i
        if name is not None:
            attempts[name] = attempts.get(name, 0) + 1
            shape = _function_shape(segments, i, body_at, top)
            if shape is not None and _FUNCTION_NAME_RE.fullmatch(name) and \
                    name not in _KEYWORDS and name not in _COMPOUND_OPEN:
                body, close = shape
                defined[name] = (i, close, body)
                i = close + 1
                continue
        depth += _compound_balance(words)
        i += 1
    calls: dict = {}
    skip: set = set()
    for name, (first, last, body) in ([] if blocked else defined.items()):
        if attempts[name] != 1 or not body or body[0] in attempts or \
                any(re.search(r"[$`]|__dwsub", w) and not _POSITIONAL_RE.fullmatch(w)
                    and w not in ('"$@"', "$@") for w in body):
            continue
        sites = [k for k in range(last + 1, len(segments)) if segments[k]["words"][:1] == [name]]
        mentions = re.findall(r"(?<![\w.-])%s(?![\w.-])" % re.escape(name), text)
        if len(mentions) != 1 + len(sites) or every.count(name) != 1 + len(sites):
            continue
        skip.update(range(first, last + 1))
        for k in sites:
            calls[k] = _call_segment(segments[k], body, attempts)
    # A call of any other function the command defines runs code that was not read.
    resolved = {segments[k]["words"][0] for k in calls}
    for k, seg in enumerate(segments):
        name = seg["words"][0] if seg["words"] else None
        if name in attempts and name not in resolved and k not in skip and \
                not _is_definition(segments, k):
            calls[k] = None
    return calls, skip


def _is_definition(segments: list, k: int) -> bool:
    """Whether segment `k` is the name part of a function definition (`name` before `(`)."""
    words = segments[k]["words"]
    return (len(words) == 1 and segments[k]["after"] == "(") or words[:1] == ["function"]


def _function_shape(segments: list, at: int, body_at: int, top: bool) -> Optional[tuple]:
    """(body words, index of the closing `}`) of a definition starting at segment `at` whose
    `{ body` is at `body_at` (or `{` alone on its line, the body on the next), when it has
    exactly the readable shape; otherwise None."""
    if not top or body_at + 1 >= len(segments):
        return None
    seg = segments[body_at]
    brace_line = body_at != at and seg["words"] == ["{"] and seg["before"] == ")" and \
        seg["after"] == "\n" and not seg["redirects"] and not seg["heredocs"]
    if brace_line:
        if body_at + 2 >= len(segments) or segments[body_at + 1]["before"] != "\n" or \
                segments[body_at + 1]["depth"] != 0:
            return None
        seg = {**segments[body_at + 1], "words": ["{"] + segments[body_at + 1]["words"],
               "before": ")"}
        body_at += 1
    close = segments[body_at + 1]
    words = seg["words"]
    if body_at == at:
        if len(words) < 4 or words[2] != "{":
            return None
        body = words[3:]
    else:
        if seg["before"] != ")" or seg["depth"] != 0 or words[:1] != ["{"] or len(words) < 2:
            return None
        body = words[1:]
    if seg["after"] not in (";", "\n") or seg["pipe_in"] or seg["pipe_out"] or \
            seg["redirects"] or seg["heredocs"] or seg["keep"]:
        return None
    if close["words"] != ["}"] or close["before"] not in (";", "\n") or close["depth"] != 0 or \
            close["after"] not in ("", ";", "\n") or close["redirects"] or close["heredocs"] or \
            close["pipe_out"]:
        return None
    return body, body_at + 1


def _call_segment(call: dict, body: list, functions: dict) -> Optional[dict]:
    """The segment a call runs: the body with the call's arguments put in. None: unreadable."""
    args = call["words"][1:]

    def splits(arg: str) -> bool:
        if re.search(r"[$`]|__dwsub", arg):
            return False  # a run-time value: kept as written, judged where it lands
        try:
            value = " ".join(shlex.split(arg))
        except ValueError:
            return True
        return bool(re.search(r"[\s*?\[{]", value))

    words: list = []
    for w in body:
        m = _POSITIONAL_RE.fullmatch(w)
        if w == '"$@"':
            words += args
        elif w == "$@":
            if any(splits(a) for a in args):
                return None
            words += args
        elif m:
            n = int(next(g for g in m.groups() if g))
            quoted = w.startswith('"')
            if n <= len(args):
                if not quoted and splits(args[n - 1]):
                    return None
                words.append(args[n - 1])
            elif quoted:
                words.append("''")
        else:
            words.append(w)
    if words[:1] and words[0] in functions:
        return None  # it calls a function this command defines
    return {**call, "words": words}
