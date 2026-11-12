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
    return {"words": [], "redirects": [], "reads": [], "heredocs": [], "pipe_in": pipe_in,
            "pipe_out": False, "keep": False}


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
                self.flat = False
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
                self.flat = False
                self.seg["words"].append(self.substitution(self.i + 2))
            elif c in "()":
                self.flat = False
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
            for _delim, _strip, seg, _quoted in self.pending:
                seg["heredocs"].append("")
        return self

    def end(self, pipe: bool = False) -> None:
        seg = self.seg
        seg["pipe_out"] = pipe
        if seg["words"] or seg["redirects"] or seg["heredocs"] or seg["keep"]:
            self.segments.append(seg)
        self.seg = _new_segment(pipe)

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
