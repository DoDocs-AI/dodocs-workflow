"""Per-project automatic approvals: registry entries that let a named guarded action through
without a question.

An entry is `{"rule": RULE_ID, "match": REGEX, "in": DIRECTORY (optional), "note": TEXT,
"added_at": EPOCH}`. A match of a shell command is covered when an entry has its rule id, the
regex fully matches the match's full segment text (the text the approval identity uses), and,
with `in`, the directory the guard tracks for that segment is that directory or inside it.

Entries come from the registry, a plain file: the guard treats them as untrusted. A malformed
entry, a regex that does not compile, one longer than MAX_PATTERN, one with a nested
quantifier or an unbounded quantifier on a group (catastrophic backtracking), one holding a
control or format character, or one that fully matches every one of a fixed set of unrelated
commands (`_PROBES`) is ignored; an entry for `control-unreadable` must also not match the
empty string nor more than one of those commands. A `control` rule is never auto-approved.
The CLI refuses the same entries (`check_entry` is shared) and `dw doctor` reports them.
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Optional

UNREADABLE_ID = "control-unreadable"
MAX_PATTERN = 2000
MAX_SEGMENT = 8192  # a longer segment is never matched
_RULE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
# A group holding a quantifier, itself quantified: (a+)+, (a|b*)*, (x{2,})+ ...
_NESTED_QUANTIFIER_RE = re.compile(r"\((?:[^()\\]|\\.)*(?:[+*]|\{\d*,?\d*\})(?:[^()\\]|\\.)*\)"
                                   r"\s*(?:[+*]|\{\d*,?\d*\})")
_UNBOUNDED_RE = re.compile(r"[*+]|\{\d*,\}")
# Unrelated single-line actions: no pattern for one kind of action matches all of them, and a
# pattern for unreadable commands matches at most one.
_PROBES = ("kubectl $(cat v) ns prod", 'gh pr "$(cat v)" 12', "git push origin main", "rm -rf /",
           "a", "zz zz", "npm publish", "docker push x/y:z", "x", "0", "é", "~/.claude")


def _quantified_group(pattern: str) -> bool:
    """Whether an unbounded quantifier (`*`, `+`, `{n,}`, lazy or not) applies to a group, read
    with escapes and character classes respected."""
    i, in_class = 0, False
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
            if pattern[i + 1:i + 2] == "^":
                i += 1
            if pattern[i + 1:i + 2] == "]":
                i += 1  # a `]` right after `[` or `[^` is a literal
        elif ch == ")" and _UNBOUNDED_RE.match(pattern, i + 1):
            return True
        i += 1
    return False


_CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")
UNSAFE_TEXT = ("a control character or a Unicode format character (line break, tab, escape, "
               "bidirectional or zero-width mark)")


class EntryError(ValueError):
    pass


def has_unsafe_char(text: str) -> bool:
    """Whether text holds a control character (line breaks and tabs included) or a format
    character (category Cf: bidirectional overrides, zero-width marks...): text the owner
    could read differently from what it is, so never part of an automatic approval."""
    return bool(_CONTROL_RE.search(text)) or any(unicodedata.category(ch) == "Cf" for ch in text)


def is_control_rule(rule: str) -> bool:
    return rule.startswith("control-") and rule != UNREADABLE_ID


def check_entry(entry) -> "re.Pattern":
    """The compiled regex of a valid entry; raises EntryError saying what is wrong."""
    if not isinstance(entry, dict):
        raise EntryError("not an object")
    rule, pattern, where = entry.get("rule"), entry.get("match"), entry.get("in")
    if not isinstance(rule, str) or not _RULE_ID_RE.match(rule):
        raise EntryError("rule is not a rule id")
    if is_control_rule(rule):
        raise EntryError("rule %s protects the control point and is never auto-approved" % rule)
    if not isinstance(pattern, str) or not pattern:
        raise EntryError("match is not a non-empty string")
    if len(pattern) > MAX_PATTERN:
        raise EntryError("match is longer than %d characters" % MAX_PATTERN)
    if where is not None and (not isinstance(where, str) or not os.path.isabs(where)):
        raise EntryError("in is not an absolute directory")
    if has_unsafe_char(pattern):
        raise EntryError("match contains " + UNSAFE_TEXT)
    if where is not None and has_unsafe_char(where):
        raise EntryError("in contains " + UNSAFE_TEXT)
    if not isinstance(entry.get("note", ""), str):
        raise EntryError("note is not text")
    if entry.get("added_at") is not None and not isinstance(entry.get("added_at"), (int, float)):
        raise EntryError("added_at is not a number")
    if _NESTED_QUANTIFIER_RE.search(pattern):
        raise EntryError("match has a nested quantifier")
    if _quantified_group(pattern):
        raise EntryError("match has an unbounded quantifier (*, +, {n,}) on a group")
    try:
        compiled = re.compile(pattern)
    except (re.error, RecursionError, OverflowError, ValueError) as exc:
        raise EntryError("match is not a valid regular expression (%s)" % exc)
    hits = sum(1 for p in _PROBES if compiled.fullmatch(p))
    if hits == len(_PROBES):
        raise EntryError("match must not match everything")
    if rule == UNREADABLE_ID and (pattern.strip() in (".*", ".+") or compiled.fullmatch("")):
        raise EntryError("an unreadable entry must not match everything")
    if rule == UNREADABLE_ID and hits >= 2:
        raise EntryError("an unreadable entry must not match more than one unrelated command "
                         "(it matches %d of: %s)" % (hits, "; ".join(
                             p for p in _PROBES if compiled.fullmatch(p))))
    return compiled


def valid_entries(project: dict) -> tuple:
    """([(entry, compiled regex)], [problem text]) for a project's `auto_approve`."""
    raw = (project or {}).get("auto_approve")
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], ["auto_approve of project %s is not a list" % (project or {}).get("id")]
    good, problems = [], []
    for n, entry in enumerate(raw, 1):
        try:
            good.append((entry, check_entry(entry)))
        except EntryError as exc:
            problems.append("project %s entry %d: %s" % ((project or {}).get("id"), n, exc))
    return good, problems


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def covers(entries: list, rule: str, segment: str, directory: Optional[str]) -> bool:
    """Whether a valid entry covers one match (rule id, full segment text, tracked directory)."""
    if is_control_rule(rule) or not isinstance(segment, str) or len(segment) > MAX_SEGMENT:
        return False
    for entry, compiled in entries:
        if entry["rule"] != rule or not compiled.fullmatch(segment):
            continue
        where = entry.get("in")
        if where is None:
            return True
        if directory and os.path.isabs(directory) and _inside(
                os.path.realpath(directory), os.path.realpath(where)):
            return True
    return False


def exact_entry(rule: str, segment: str, directory: str, note: str, now: float) -> dict:
    """The entry that covers exactly one action: its segment, escaped, in its directory."""
    return {"rule": rule, "match": re.escape(segment), "in": directory, "note": note,
            "added_at": now}
