"""Paths of the approval guard: which files are the control point's own (_Protected), and
which programs only read the files they are given (_READ_ONLY). The rule for what the parser
cannot read is in guard.py's module docstring."""
from __future__ import annotations

import os
import posixpath
import re
import stat
from pathlib import Path
from typing import Optional

from . import paths
from .guard_shell import _TooMany, _bounded_glob, _brace_expand, _home, _inside


def settings_path() -> Path:
    override = os.environ.get("DW_CLAUDE_SETTINGS")
    return Path(override) if override else Path(_home()) / ".claude" / "settings.json"


# -- protected paths -----------------------------------------------------------
#
# One model for every path check. A word in a WRITE position (see _write_positions) is a
# path pattern: fixed text, glob parts (* ? [..], never crossing "/") and run-time parts
# (variables, substitutions, text from standard input; they may cross "/"). Braces are
# expanded first, ~, $HOME and $DW_HOME are filled in. The word is held when the pattern
# may name one of the control point's files, judged two ways:
#   by name      a segment names a protected directory (.git, .claude, agterm, .agterm,
#                .dodocs-workflow) and what follows may be a protected file in it;
#   by real path the fixed leading directories, resolved against the working directory and
#                through symbolic links, lead to a protected real path the rest may match.

# The files git reads its configuration, hooks and attributes from, relative to a git dir
# (worktree and submodule git dirs included).
_GIT_FILES = r"(?:(?:worktrees|modules)/.+/)?(?:config|config\.worktree|info/attributes|hooks(?:/.*)?)"
_GIT_FILES_RE = re.compile(r"^%s$" % _GIT_FILES, re.I)
_GIT_INTERNAL_RE = re.compile(r"/\.git/%s$" % _GIT_FILES, re.I)
_GIT_DIR_CHILDREN = ("hooks", "info", "config", "config.worktree", "worktrees", "modules")
# Protected directory names, and the protected files directly inside each (None: git's own
# list above; (): everything).
_PROTECTED_NAMES = {".git": None, ".dodocs-workflow": (),
                    ".claude": ("settings.json", "settings.local.json"),
                    "agterm": ("hooks.conf",), ".agterm": ("hooks.conf",)}
# A run-time part of a word: a variable, a substitution placeholder, or stdin text.
_RUN_TIME_PART_RE = re.compile(
    r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]|__dwsub(\d+)__|__dwsub_input__|`[^`]*`")
# A git dir by reference: these variables, or `git rev-parse` asked for the git dir.
_GIT_DIR_VAR_RE = re.compile(r"^\$\{?(GIT_DIR|GIT_COMMON_DIR)(?![A-Za-z0-9_])")
_GIT_DIR_SUB_RE = re.compile(r"\bgit\b.*\brev-parse\b.*--(git-dir|git-common-dir|absolute-git-dir|"
                             r"git-path)(?![\w-])", re.S)
_GIT_PATH_SUB_RE = re.compile(r"--git-path[ =]+['\"]?([\w./-]+)")
_DW_HOME_VAR_RE = re.compile(r"\$\{DW_HOME(?![A-Za-z0-9_])[^}]*\}|\$DW_HOME(?![A-Za-z0-9_])")
_GLOB_PART_RE = re.compile(r"\[[^\]/]*\]|[*?]")
# In a path skeleton a run-time part is one of these characters; _GIT_ANY is a run-time
# part that stands for a git dir ($GIT_DIR, $(git rev-parse --git-dir), see _GIT_DIR_*_RE).
_ANY, _GIT_ANY = "\x01", "\x02"  # not NUL: os.path.normpath stops at one
_RUN_TIME_MARKS_RE = re.compile("[\x01\x02]+")
MAX_WILDCARDS = 6  # in a path matched part by part against a real path


def _run_time(seg: str) -> bool:
    return _ANY in seg or _GIT_ANY in seg


def _wild(seg: str) -> bool:
    return _run_time(seg) or bool(_GLOB_PART_RE.search(seg))


def _wildcards(text: str) -> int:
    return len(_RUN_TIME_MARKS_RE.findall(text)) + len(_GLOB_PART_RE.findall(text))


_WILD_PART_RE = re.compile("%s|%s" % (_RUN_TIME_MARKS_RE.pattern, _GLOB_PART_RE.pattern))


def _segment_regex(seg: str) -> str:
    """A regular expression for one segment of a path skeleton, to match against a real
    path. A run-time part may be any text; a glob part stays inside the segment, and a
    leading one does not match a dot file."""
    rx = r"(?!\.)" if seg[:1] in ("*", "?", "[") else ""
    pos = 0
    for m in _WILD_PART_RE.finditer(seg):
        part = m.group(0)
        rx += re.escape(seg[pos:m.start()])
        rx += ".*" if part[0] in (_ANY, _GIT_ANY) else "[^/]*" if part == "*" else "[^/]"
        pos = m.end()
    return rx + re.escape(seg[pos:])


def _may_equal(pattern: str, text: str) -> bool:
    """May a skeleton be exactly `text`, taking every wildcard part as "any text"? Its fixed
    chunks must occur in `text` in order, the first at the start and the last at the end.
    Linear, and never says no to something a glob could match."""
    chunks = _WILD_PART_RE.split(pattern.lower())
    text = text.lower()
    if len(chunks) == 1:
        return chunks[0] == text
    first, last = chunks[0], chunks[-1]
    if len(first) + len(last) > len(text) or not text.startswith(first) or not text.endswith(last):
        return False
    pos, end = len(first), len(text) - len(last)
    for chunk in chunks[1:-1]:
        pos = text.find(chunk, pos, end)
        if pos < 0:
            return False
        pos += len(chunk)
    return True


def _could_be(seg: str, name: str) -> bool:
    """May this segment be `name`? A segment made of wildcards only names nothing: a bare
    `$D/settings.json` is not a path under .claude."""
    if not _wild(seg):
        return seg.lower() == name
    if not _RUN_TIME_MARKS_RE.sub("", _GLOB_PART_RE.sub("", seg)):
        return False
    return _may_equal(seg, name)


def _may_be_path(segs: list, path: str) -> bool:
    """May these skeleton segments be exactly the relative real path `path`? Exact about
    which parts may cross "/" while the wildcard parts are few; beyond that, by the fixed
    chunks only (_may_equal), which costs no backtracking."""
    if _wildcards("/".join(segs)) > MAX_WILDCARDS:
        return _may_equal("/".join(segs), path)
    rx = "/".join(_segment_regex(seg) for seg in segs)
    return bool(re.fullmatch(rx, path, re.I | re.S))


class _Protected:
    """The control point's own files."""

    def __init__(self, run_id: Optional[str]):
        home = _home()
        # Compared in lower case: the file system may ignore case (macOS does by default).
        self.dw_home = os.path.realpath(str(paths.home()))
        self.dirs = sorted({self.dw_home.lower(),
                            os.path.realpath(os.path.join(home, ".dodocs-workflow")).lower()})
        self.files = {os.path.realpath(os.path.join(home, ".claude", "settings.json")).lower(),
                      os.path.realpath(str(settings_path())).lower(),
                      os.path.realpath(os.path.join(home, ".config", "agterm", "hooks.conf")).lower()}
        self.home = os.path.realpath(home).lower()
        # The run's result note, its last component NOT followed: if the note is a symlink, a
        # write to it is a write to wherever the link points, and that is judged instead.
        note = str(paths.result_note_path(run_id)) if run_id else None
        self.note_path = os.path.join(os.path.realpath(os.path.dirname(note)),
                                      os.path.basename(note)) if note else None
        self.note = self.note_path.lower() if note else None
        # Whether a write to the note may be spared in the call being read: classify sets it
        # (the Write or Edit tool, or a plain Bash write: see guard._plain_note_write).
        self.note_spared = False
        self.markers = [".dodocs-workflow", "agterm/hooks.conf"] + self.dirs + sorted(self.files)

    def note_exempt(self, path: str) -> bool:
        """Whether a write to `path` (a real path) is the run's own result note and spared: the
        word being judged is one the guard spares (`note_spared`), and the note exists as a
        regular file with one link, with no symlink at it or between it and DW_HOME."""
        if not self.note or path.lower() != self.note or not self.note_spared:
            return False
        runs = os.path.join(self.dw_home, "runs")
        try:
            if os.path.islink(runs) or os.path.realpath(runs) != os.path.dirname(self.note_path):
                return False  # a symlink below the state directory
            info = os.lstat(self.note_path)
        except OSError:
            return False  # missing: dw creates it empty at launch
        return stat.S_ISREG(info.st_mode) and info.st_nlink == 1

    def names_note(self, word: str, cwd: Optional[str], bodies=(), marks=()) -> bool:
        """Whether a word may name the note path itself (its last component not followed). A
        pattern counts when its directory is the note's (it may name the note)."""
        if not self.note:
            return False
        for skel in self._skeletons(word, list(bodies or []), marks):
            if not skel or (not os.path.isabs(skel) and cwd is None):
                continue
            full = os.path.join(cwd or "/", skel)
            head, tail = os.path.split(full)
            if not tail:
                continue
            if _wild(skel):
                if not _wild(head) and os.path.realpath(head).lower() == \
                        os.path.dirname(self.note):
                    return True
                continue
            if os.path.join(os.path.realpath(head), tail).lower() == self.note:
                return True
        return False

    def _only_the_note(self, token: str, cwd: Optional[str], bodies: list, marks) -> bool:
        """Every reading of the word is exactly the run's result note, and it is spared."""
        skels = self._skeletons(token, bodies, marks)
        return bool(skels) and all(
            skel and not _wild(skel) and (os.path.isabs(skel) or cwd is not None)
            and self.note_exempt(os.path.realpath(os.path.join(cwd or "/", skel)))
            for skel in skels)

    def hit(self, path: str) -> bool:
        """A real path without wildcards."""
        if self.note_exempt(path):
            return False
        path = path.lower()
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

    def _skeletons(self, word: str, bodies: list, marks) -> list:
        """The paths a word stands for: ~, $HOME and $DW_HOME filled in, the other run-time
        parts (and xargs, parallel or find replace strings) turned into markers, braces
        expanded. Braces too many to expand become run-time parts."""
        home = _home()
        text = _DW_HOME_VAR_RE.sub(lambda m: self.dw_home, word)
        text = text.replace("${HOME}", home).replace("$HOME", home)
        for mark in marks:
            text = text.replace(mark, "__dwsub_input__")

        def marker(m):
            if m.group(1) is None:
                return _GIT_ANY if _GIT_DIR_VAR_RE.match(m.group(0)) else _ANY
            body = bodies[int(m.group(1))] if int(m.group(1)) < len(bodies) else ""
            if not _GIT_DIR_SUB_RE.search(body):
                return _ANY
            below = _GIT_PATH_SUB_RE.search(body)  # --git-path hooks: the git dir, then hooks
            return _GIT_ANY + ("/" + below.group(1) if below else "")

        text = _RUN_TIME_PART_RE.sub(marker, text)
        try:
            found = _brace_expand(text) if "{" in text else [text]
        except _TooMany:
            found = [re.sub(r"[{}]", _ANY, text)]
        out = []
        for one in found:
            if one == "~" or one.startswith("~/"):
                one = home + one[1:]
            elif one.startswith("~"):
                one = os.path.expanduser(one)
            out.append(one)
        return out

    def _named(self, segs: list) -> bool:
        """By name: some segment names a protected directory, and the rest of the path may
        be a protected file in it."""
        for i, seg in enumerate(segs):
            tail = segs[i + 1:]
            for name, files in _PROTECTED_NAMES.items():
                if not _could_be(seg, name):
                    continue
                if _wild(seg):
                    # The name itself is a pattern: hold when anything follows, or when a
                    # run-time part ends the segment (it may hold the rest of the path).
                    if tail or seg[-1] in (_ANY, _GIT_ANY):
                        return True
                elif self._file_in(files, tail):
                    return True
            if _GIT_ANY in seg and self._git_dir_child(tail):
                return True
        return False

    def names(self, skel: str) -> bool:
        """The by-name check of one skeleton, whatever the working directory is. It looks at
        the segments as written and as normalised. ".." is not resolved across a wildcard
        segment (nobody knows what it cancels): such a path is held when any segment may be
        a protected directory."""
        segs = [s for s in skel.split("/") if s and s != "."]
        wild_before, undecided = False, False
        for seg in segs:
            undecided = undecided or (seg == ".." and wild_before)
            wild_before = wild_before or _wild(seg)
        if undecided:
            return any(_GIT_ANY in seg or any(_could_be(seg, name) for name in _PROTECTED_NAMES)
                       for seg in segs)
        normal = [s for s in posixpath.normpath(skel).split("/") if s and s != "."]
        return self._named(segs) or (normal != segs and self._named(normal))

    def text_names(self, text: str) -> bool:
        """Whether a word of literal text (in a substitution, or sent to xargs) spells a
        protected path by name."""
        word = text.strip("'\"")
        if not word or len(word) > 4096 or "\0" in word:
            return False
        return any(skel and self.names(skel) for skel in self._skeletons(word, [], ()))

    def words_name(self, words: list) -> bool:
        """Whether a command whose output is used as a path (in a substitution, or piped to
        xargs or `while read`) spells a protected path in its words. Only cat, head and tail
        without options do not count: they give out what is in the file, not its name."""
        if words[:1] and words[0] in ("cat", "head", "tail") and \
                not any(_is_option(w) for w in words[1:]):
            return False
        return any(self.text_names(w) for w in words[1:])

    @staticmethod
    def _file_in(files, tail: list) -> bool:
        """May `tail`, the segments after a protected directory's name, be one of its
        protected files? A run-time part may hold "/" and "..": then only the last segment
        decides. A glob part stays inside its segment."""
        wild = any(_wild(s) for s in tail)
        if files is None:  # .git: hooks/ takes any name, so any wildcard may reach one
            return wild or bool(_GIT_FILES_RE.match("/".join(tail)))
        if not files:  # .dodocs-workflow: everything in it, and the directory itself
            return True
        if not tail:
            return False
        last = tail[-1]
        if not wild:
            return len(tail) == 1 and last.lower() in files
        if len(tail) > 1 and not any(_run_time(s) for s in tail):
            return False
        return last[-1] in (_ANY, _GIT_ANY) or any(_may_equal(last, f) for f in files)

    @staticmethod
    def _git_dir_child(tail: list) -> bool:
        """After a git dir given by reference: the fixed rest is one of git's own files; or
        the first segment is one of git's directories (hooks, info, worktrees, modules) and it
        ends the path or a wildcard follows; or it starts with "config" and ends the path;
        or it is a pattern that may be one of those names."""
        if not tail:
            return False
        first, rest = tail[0], tail[1:]
        if not any(_wild(s) for s in tail) and _GIT_FILES_RE.match("/".join(tail)):
            return True
        if _wild(first):
            return any(_could_be(first, child) for child in _GIT_DIR_CHILDREN)
        if first.lower().startswith("config"):
            return not rest  # git's config is a file: nothing of git's lies below it
        return first.lower() in _GIT_DIR_CHILDREN and (not rest or any(_wild(s) for s in rest))

    def _real_targets(self, rdir: str) -> tuple:
        """(files, directories) protected as real paths: the control point's own, and those
        of a .git, .claude or agterm directory that `rdir` is or is inside."""
        files, dirs = set(self.files), set(self.dirs)
        parts = rdir.split("/")
        for k in range(1, len(parts) + 1):
            names = _PROTECTED_NAMES.get(parts[k - 1])
            above = "/".join(parts[:k])
            if parts[k - 1] == ".git":
                files |= {above + "/config", above + "/config.worktree", above + "/info/attributes"}
                dirs.add(above + "/hooks")
            elif names:
                files |= {above + "/" + n for n in names}
        return files, dirs

    def _real_hit(self, skel: str, cwd: Optional[str]) -> bool:
        """By real path: resolve the fixed leading directories; may the rest name a protected
        real path below them? Glob-only patterns are also expanded on disk."""
        segs = [s for s in skel.split("/") if s]
        k = next((i for i, s in enumerate(segs) if _wild(s)), None)
        if k is None:
            return False
        absolute = skel.startswith("/")
        if not absolute and cwd is None:
            return False  # no known directory to start from
        real = os.path.realpath(os.path.join("/" if absolute else cwd, *segs[:k]))
        rdir, rest = real.lower(), segs[k:]
        files, dirs = self._real_targets(rdir)
        if any(_inside(rdir, d) for d in dirs):
            return True
        below = rdir.rstrip("/") + "/"
        files = [f[len(below):] for f in files if f.startswith(below)]
        dirs = [d[len(below):] for d in dirs if d.startswith(below)]
        if any(_may_be_path(rest, f) for f in files):
            return True
        if dirs:  # the pattern names the directory, or goes through it
            if any(_may_be_path(rest[:i], d) for i in range(1, len(rest) + 1) for d in dirs):
                return True
        if any(_run_time(s) for s in rest):
            return False
        try:
            found, complete = _bounded_glob(os.path.join(real, *rest))
        except (re.error, ValueError):
            return False
        if not complete:
            return True  # too much to look at: cannot decide, so hold
        return any(self.hit(os.path.realpath(f)) for f in found)

    def text_hit(self, text: str) -> bool:
        clean = text.replace("\\", "").lower()
        return any(m in clean for m in self.markers) or \
            bool(re.search(r"\.claude/settings(\.local)?\.json", clean))

    def token_hit(self, token: str, cwd: Optional[str], bodies: Optional[list] = None,
                  marks=()) -> bool:
        """Whether a word in a write position may name one of the control point's files."""
        if self.note_spared and self._only_the_note(token, cwd, bodies or [], marks):
            return False
        candidates = [token]
        if "=" in token:
            candidates.append(token.split("=", 1)[1])
        if re.match(r"-[A-Za-z][^=]", token):
            candidates.append(token[2:])  # a value attached to a short option (-O.git/config)
        for cand in candidates:
            if not cand or len(cand) > 4096 or "\n" in cand or "\0" in cand or \
                    cand in ("[", "[[", "{", "}"):
                continue
            for skel in self._skeletons(cand, bodies or [], marks):
                if not skel:
                    continue
                if not _wild(skel) and (os.path.isabs(skel) or cwd is not None):
                    resolved = os.path.realpath(os.path.join(cwd or "/", skel))
                    if self.note_exempt(resolved):
                        continue  # this reading is the note; the word's other readings count
                    if self.hit(resolved):
                        return True
                if self.names(skel):
                    return True
                if _wild(skel) and self._real_hit(posixpath.normpath(skel), cwd):
                    return True
            # A substitution inside the word: the literal text of what it runs may spell the path.
            for m in _RUN_TIME_PART_RE.finditer(cand):
                if m.group(1) is not None and int(m.group(1)) < len(bodies or []):
                    words = bodies[int(m.group(1))].split()
                    if self.words_name(words):
                        return True
        return self.text_hit(token)


def _sed_scripts_only_print(tokens: list) -> bool:
    """Every sed script on the line is one this guard knows to write nothing and run nothing:
    an address with p, d or q, or a plain substitution with the flags g, p, i, I or a
    number. (w, W and e, as commands or as flags of s, write files and run commands.)"""
    scripts, operands, i = [], [], 1
    while i < len(tokens):
        t = tokens[i]
        if t in ("-e", "--expression") and i + 1 < len(tokens):
            scripts.append(tokens[i + 1])
            i += 1
        elif t.startswith("--expression="):
            scripts.append(t.split("=", 1)[1])
        elif not _is_option(t):
            operands.append(t)
        i += 1
    scripts = scripts or operands[:1]
    return bool(scripts) and all(_SED_SCRIPT_RE.fullmatch(script) for script in scripts)


_SED_ADDRESS = r"(?:[0-9,$]*|/[^/\n]*/(?:,/[^/\n]*/)?)"
_SED_SCRIPT_RE = re.compile(
    r"\s*%s\s*(?:[pdq]|s([^\w\s\\])(?:(?!\1)[^\n\\]|\\.)*\1(?:(?!\1)[^\n\\]|\\.)*\1[gpiI0-9]*)\s*"
    % _SED_ADDRESS)


def _awk_program_only_prints(tokens: list) -> bool:
    return not any(re.search(r"system\s*\(|\||>|getline", t) for t in tokens[1:])


def _read_only(short: str = r"-.*", long: str = "", operands: Optional[int] = None, check=None):
    """One read-only program: its short options that write nothing, its long options that
    write nothing (an allowlist: GNU programs accept any unambiguous prefix of a long
    option, so a list of the ones that write could be walked around), the most operands it
    may have, and a test of the whole line."""
    return (re.compile(short, re.S), re.compile(r"--(?:help|version%s)" % ("|" + long if long else ""),
                                                re.S), operands, check)


_DIGEST = _read_only(long=r"algorithm=.*|check|binary|text|tag|quiet|status|warn|strict|zero|"
                          r"ignore-missing")
_LESS = _read_only(r"-[^-oO=][^oO=]*",  # not -o, -O, --log-file
                   r"quit-if-one-screen|RAW-CONTROL-CHARS|raw-control-chars|chop-long-lines|"
                   r"LINE-NUMBERS|line-numbers|no-init|ignore-case|IGNORE-CASE")
_AWK = _read_only(r"-F.*|-v", check=_awk_program_only_prints)  # not -f, -i inplace
_FILE_TEST_OPS = {"-e", "-f", "-d", "-s", "-r", "-w", "-x", "-L", "-h", "-p", "-S", "-b", "-c",
                  "-g", "-u", "-k", "-O", "-G", "-N", "!", "-a", "-o", "&&", "||", "(", ")",
                  "]", "]]"}
_TEST_OPERATORS = {"=", "==", "!=", "=~", "<", ">"}


def _only_file_tests(tokens: list) -> bool:
    """test, [ and [[ only read when every word is a unary file test, a connective or a plain
    path: an arithmetic operand (-eq family, -v) can run a substitution in an array subscript,
    so any other operator, and any operand with `[`, `$` or a backquote, is not exempt."""
    for word in tokens[1:]:
        if word in _FILE_TEST_OPS:
            continue
        if word.startswith("-") or word in _TEST_OPERATORS or "__dwsub" in word or \
                any(c in word for c in "[$`"):
            return False
    return True


_FILE_TEST = _read_only(long=r".*", check=_only_file_tests)
_READ_ONLY = {
    "echo": _read_only(long=r".*"), "printf": _read_only(long=r".*"),  # their words are text
    "cat": _read_only(long=r"number|number-nonblank|show-all|show-ends|show-tabs|"
                           r"show-nonprinting|squeeze-blank"),
    "ls": _read_only(long=r"all|almost-all|human-readable|color(=.*)?|group-directories-first|"
                          r"recursive|reverse|sort=.*|time=.*|time-style=.*|size|classify|"
                          r"directory|inode|no-group|format=.*|full-time|literal|si"),
    "head": _read_only(long=r"lines=.*|bytes=.*|quiet|silent|verbose|zero-terminated"),
    "tail": _read_only(long=r"lines=.*|bytes=.*|quiet|silent|verbose|zero-terminated|"
                            r"follow(=.*)?|retry|pid=.*|sleep-interval=.*"),
    "wc": _read_only(long=r"lines|words|bytes|chars|max-line-length"),
    "du": _read_only(long=r"human-readable|summarize|max-depth=.*|total|all|apparent-size|"
                          r"block-size=.*|exclude=.*|si|bytes|one-file-system"),
    "stat": _read_only(long=r"format=.*|printf=.*|terse|dereference|file-system"),
    "grep": _read_only(long=r"colou?r(=.*)?|include(=.*)?|exclude(=.*)?|exclude-dir(=.*)?|"
                            r"recursive|dereference-recursive|line-number|ignore-case|"
                            r"extended-regexp|fixed-strings|perl-regexp|basic-regexp|invert-match|"
                            r"word-regexp|line-regexp|count|files-with-matches|"
                            r"files-without-match|only-matching|quiet|silent|no-filename|"
                            r"with-filename|null|text|binary-files=.*|max-count=.*|"
                            r"context(=.*)?|after-context(=.*)?|before-context(=.*)?|no-messages|"
                            r"line-buffered|regexp(=.*)?|byte-offset|initial-tab|null-data"),
    "diff": _read_only(long=r"unified(=.*)?|context(=.*)?|recursive|brief|ignore-[a-z-]+(=.*)?|"
                            r"side-by-side|colou?r(=.*)?|new-file|exclude=.*|label=.*|text|"
                            r"strip-trailing-cr|minimal|report-identical-files|width=.*|"
                            r"suppress-common-lines|show-c-function|expand-tabs|normal"),
    "basename": _read_only(long=r"suffix=.*|multiple|zero"),
    "dirname": _read_only(long=r"zero"),
    "realpath": _read_only(long=r"relative-to=.*|relative-base=.*|canonicalize-existing|"
                                r"canonicalize-missing|no-symlinks|physical|logical|quiet|zero|"
                                r"strip"),
    "jq": _read_only(long=r"arg|argjson|slurp|raw-output|raw-input|null-input|compact-output|tab|"
                          r"indent|sort-keys|color-output|monochrome-output|exit-status|"
                          r"join-output|slurpfile|rawfile|args|jsonargs|from-file|stream|seq|"
                          r"ascii-output"),
    "cut": _read_only(long=r"delimiter=.*|fields=.*|bytes=.*|characters=.*|complement|"
                           r"only-delimited|output-delimiter=.*|zero-terminated"),
    "tr": _read_only(long=r"delete|squeeze-repeats|complement|truncate-set1"),
    "column": _read_only(long=r"table|separator(=.*)?|output-separator(=.*)?|json|"
                              r"table-columns(=.*)?|fillrows"),
    "od": _read_only(long=r"address-radix=.*|format=.*|read-bytes=.*|skip-bytes=.*|"
                          r"width(=.*)?|output-duplicates|endian=.*"),
    "strings": _read_only(long=r"all|bytes=.*|radix=.*|encoding=.*|print-file-name"),
    "md5": _DIGEST, "md5sum": _DIGEST, "shasum": _DIGEST, "sha1sum": _DIGEST, "sha256sum": _DIGEST,
    "file": _read_only(r"-[^-C]*", r"mime(-type|-encoding)?|brief|dereference|no-dereference|"
                                   r"uncompress|separator=.*"),  # not -C, --compile
    "less": _LESS, "more": _LESS,
    "tree": _read_only(r"-[^-oR=][^oR=]*",  # not -o, --output
                       r"charset=.*|dirsfirst|gitignore|noreport|prune|du|si"),
    "rg": _read_only(long=r"glob(=.*)?|iglob(=.*)?|files|files-with-matches|files-without-match|"
                          r"hidden|no-ignore[a-z-]*|ignore-case|smart-case|case-sensitive|"
                          r"line-number|no-line-number|count|count-matches|context(=.*)?|"
                          r"after-context(=.*)?|before-context(=.*)?|type(=.*)?|type-not(=.*)?|"
                          r"fixed-strings|word-regexp|invert-match|only-matching|json|"
                          r"color(=.*)?|pretty|no-heading|heading|with-filename|no-filename|"
                          r"max-count(=.*)?|max-depth(=.*)?|multiline|pcre2|regexp(=.*)?|"
                          r"sortr?(=.*)?|stats|text|follow|null|vimgrep|column|replace(=.*)?|"
                          r"passthru|quiet|trim|unrestricted|max-columns(=.*)?"),  # not --pre
    "find": _read_only(r"(?!-(delete|exec|ok|fprint|fls))-.*"),  # primaries: never abbreviated
    "sort": _read_only(r"-[^-oT=]*",  # not -o, -T, --output, --compress-program
                       r"reverse|numeric-sort|unique|key=.*|field-separator=.*|ignore-case|"
                       r"human-numeric-sort|version-sort|stable|check(=.*)?|general-numeric-sort|"
                       r"month-sort|random-sort|ignore-leading-blanks|dictionary-order|"
                       r"zero-terminated|merge"),
    "uniq": _read_only(long=r"count|repeated|unique|ignore-case|skip-fields=.*|skip-chars=.*|"
                            r"check-chars=.*|all-repeated(=.*)?|zero-terminated|group(=.*)?",
                       operands=1),  # a second operand is the output file
    "xxd": _read_only(r"-[^-r]*", operands=1),  # not -r; a second operand is the output file
    "yq": _read_only(r"-[^-i]*",  # not -i, --inplace
                     r"prettyPrint|raw-output|output-format=.*|input-format=.*|no-colors|colors|"
                     r"null-input|indent=.*|unwrapScalar(=.*)?|exit-status|no-doc"),
    "sed": _read_only(r"-[nEru]+|-[nEru]*e", r"quiet|silent|regexp-extended|posix|debug|"
                                             r"expression(=.*)?", check=_sed_scripts_only_print),
    "awk": _AWK, "gawk": _AWK, "mawk": _AWK, "nawk": _AWK,
    "test": _FILE_TEST, "[": _FILE_TEST, "[[": _FILE_TEST,  # existence checks only
    "cmp": _read_only(long=r"silent|quiet|print-bytes|verbose|bytes=.*|ignore-initial=.*"),
    "readlink": _read_only(long=r"canonicalize(-existing|-missing)?|no-newline|zero|verbose|"
                                r"quiet|silent"),
}
def _is_option(word: str) -> bool:
    return word.startswith("-") and len(word) > 1
