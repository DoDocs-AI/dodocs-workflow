#!/usr/bin/env bash
set -euo pipefail

# Validate the installers:
#   - install.sh (local mode, into a temp HOME) actually installs every agent,
#     command, docker file, and template it claims
#   - uninstall.sh AGENTS/COMMANDS arrays are identical to install.sh's
#   - uninstall.sh removes everything install.sh installed

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
UNINSTALL_SH="$REPO_ROOT/uninstall.sh"

ERRORS=0

fail() {
    echo "FAIL: $1"
    ERRORS=$((ERRORS + 1))
}

pass() {
    echo "PASS: $1"
}

# Extract a quoted bash array block (ARRAYNAME=( ... )) from a script
# (same line-based parsing as validate-structure.sh — portable across BSD/GNU)
extract_array() {
    local script="$1" arrayname="$2" inside=false line item
    while IFS= read -r line; do
        if [[ "$line" == "${arrayname}=("* ]]; then
            inside=true
            continue
        fi
        if $inside; then
            [[ "$line" == ")"* ]] && break
            item=$(echo "$line" | sed -n 's/.*"\([^"]*\)".*/\1/p')
            [ -n "$item" ] && echo "$item"
        fi
    done < "$script"
}

# ── 1. Array parity install.sh vs uninstall.sh ─────────────────────
echo ""
echo "=== Checking install.sh vs uninstall.sh array parity ==="
for arrayname in AGENTS COMMANDS; do
    diff_out=$(diff <(extract_array "$INSTALL_SH" "$arrayname") <(extract_array "$UNINSTALL_SH" "$arrayname") || true)
    if [ -z "$diff_out" ]; then
        pass "$arrayname arrays are identical in install.sh and uninstall.sh"
    else
        fail "$arrayname arrays differ between install.sh and uninstall.sh:"
        echo "$diff_out"
    fi
done
echo ""

# ── 2. Fresh install into a temp HOME ──────────────────────────────
echo "=== Running install.sh into a temp HOME (local mode) ==="
FAKE_HOME=$(mktemp -d)
trap 'rm -rf "$FAKE_HOME"' EXIT

if HOME="$FAKE_HOME" bash "$INSTALL_SH" >/dev/null 2>&1; then
    pass "install.sh completed"
else
    fail "install.sh exited non-zero"
fi

expected_agents=$(extract_array "$INSTALL_SH" AGENTS | wc -l | tr -d ' ')
installed_agents=$(find "$FAKE_HOME/.claude/agents" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "$installed_agents" = "$expected_agents" ]; then
    pass "installed $installed_agents agent files (matches AGENTS array)"
else
    fail "installed $installed_agents agent files, AGENTS array lists $expected_agents"
fi

expected_cmds=$(extract_array "$INSTALL_SH" COMMANDS | wc -l | tr -d ' ')
installed_cmds=$(find "$FAKE_HOME/.claude/commands" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "$installed_cmds" = "$expected_cmds" ]; then
    pass "installed $installed_cmds command files (matches COMMANDS array)"
else
    fail "installed $installed_cmds command files, COMMANDS array lists $expected_cmds"
fi

for f in \
    ".claude/docker/agent-env.Dockerfile" \
    ".claude/docker/agent-entrypoint.sh" \
    ".claude/skills/gtm-api-config.template.md" \
    ".claude/statusline-dodocs-workflow.sh" \
    ".claude/scrum-team-config.template.md" \
    ".claude/openspec-conventions.md" \
    ".claude/.dodocs-workflow-version"
do
    if [ -f "$FAKE_HOME/$f" ]; then
        pass "installed $f"
    else
        fail "missing after install: $f"
    fi
done

installed_version=$(cat "$FAKE_HOME/.claude/.dodocs-workflow-version" 2>/dev/null || echo "MISSING")
repo_version=$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")
if [ "$installed_version" = "$repo_version" ]; then
    pass "version file matches VERSION ($repo_version)"
else
    fail "version file is '$installed_version', VERSION is '$repo_version'"
fi
echo ""

# ── 3. Uninstall removes everything ────────────────────────────────
echo "=== Running uninstall.sh against the temp HOME ==="
if HOME="$FAKE_HOME" bash "$UNINSTALL_SH" >/dev/null 2>&1; then
    pass "uninstall.sh completed"
else
    fail "uninstall.sh exited non-zero"
fi

leftovers=$(find "$FAKE_HOME/.claude" -type f 2>/dev/null || true)
if [ -z "$leftovers" ]; then
    pass "no dodocs-workflow files left after uninstall"
else
    fail "files left after uninstall:"
    echo "$leftovers"
fi
echo ""

# ── Summary ─────────────────────────────────────────────────────────
if [ "$ERRORS" -gt 0 ]; then
    echo "FAILED: $ERRORS error(s) found."
    exit 1
else
    echo "ALL CHECKS PASSED."
    exit 0
fi
