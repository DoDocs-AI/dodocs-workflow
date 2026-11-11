"""Git side of the approval guard: push destinations, the default branch, aliases and the
config that decides where pushes go. Reads local git state only; never contacts a remote."""
from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING, Optional

from . import runs
from .guard_shell import (  # noqa: F401
    _dynamic,
    _resolve,
    _short,
    _unreadable_match,
    _word_dynamic,
)

if TYPE_CHECKING:  # annotations only; guard imports this module
    from .guard import _Ctx


# Interpreter switches: (inline-code letters, plain flag letters, letters taking a value
# (attached, or the next token), letters whose value may only be attached).
_GIT_ENV_RE = re.compile(
    r"^(GIT_CONFIG(_GLOBAL|_SYSTEM|_COUNT|_PARAMETERS|_NOSYSTEM|_KEY_\w+|_VALUE_\w+)?|GIT_DIR|"
    r"GIT_WORK_TREE|GIT_COMMON_DIR|GIT_SSH|GIT_SSH_COMMAND|GIT_SSH_VARIANT|GIT_EXEC_PATH|"
    r"GIT_ALTERNATE_OBJECT_DIRECTORIES|GIT_NAMESPACE|GIT_PROXY_COMMAND|GIT_ASKPASS)=")


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
        elif code == 128 and re.search(r"not a git repository|cannot change to",
                                       "".join(err).lower()):
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
        if ":" not in ref and not parts["delete"] and not dst.startswith("refs/tags/") \
                and dst not in ("HEAD", "@", ""):
            routed = _configured_destinations(repo, remote, dst, ctx)
            if routed is None or routed & _protected_branches(repo, remote, ctx):
                return True
            if routed:
                continue
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


def _configured_destinations(repo: Optional[str], remote: Optional[str], source: str,
                             ctx: _Ctx) -> Optional[set]:
    """Where `git push <remote> <source>` sends `source` when `remote.<remote>.push` is set:
    the destinations of the configured refspecs whose source matches. An empty set means no
    configured refspec applies (the branch keeps its name). None: cannot be read."""
    if repo is None:
        return None
    remote = remote or "origin"
    if not re.match(r"^[A-Za-z0-9._-]+$", remote):
        return set()  # a URL: no remote config applies
    kind, current = _git_head(repo, ctx)
    if kind == "norepo":
        return set()
    code, specs = _git_config_value(repo, "remote.%s.push" % remote, ctx, all_values=True)
    if code not in (0, 1):
        return None
    name = source[len("refs/heads/"):] if source.startswith("refs/heads/") else source
    out: set = set()
    for spec in specs:
        if spec.startswith("^"):
            continue
        src = spec.lstrip("+").partition(":")[0]
        applies = src in (name, "refs/heads/" + name) or \
            (src in ("HEAD", "@") and kind == "branch" and current == name) or "*" in src
        if not applies:
            continue
        found = _push_refspec_destinations(spec, current if kind == "branch" else None, [name])
        if found is None:
            return None
        out |= found
    return out


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
