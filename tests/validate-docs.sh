#!/usr/bin/env bash
set -euo pipefail

# Validate documentation:
#   - Compare actual agent/command counts with FEATURES.md claims
#   - README.md exists
# Note: count mismatches produce warnings, not failures.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_DIR="$REPO_ROOT/claude/agents"
COMMANDS_DIR="$REPO_ROOT/claude/commands"
FEATURES_MD="$REPO_ROOT/docs/FEATURES.md"
README_MD="$REPO_ROOT/README.md"

ERRORS=0
WARNINGS=0

fail() {
    echo "FAIL: $1"
    ERRORS=$((ERRORS + 1))
}

warn() {
    echo "WARN: $1"
    WARNINGS=$((WARNINGS + 1))
}

pass() {
    echo "PASS: $1"
}

# ── 1. Count actual agent files ────────────────────────────────────
echo ""
echo "=== Checking agent counts ==="
actual_agent_count=$(find "$AGENTS_DIR" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
echo "INFO: Found $actual_agent_count agent files in claude/agents/"

if [ -f "$FEATURES_MD" ]; then
    # Look for patterns like "25 agent" or "N agent definitions"
    features_agent_count=$(grep -oE '[0-9]+ agent' "$FEATURES_MD" | head -1 | grep -oE '[0-9]+' || true)
    if [ -n "$features_agent_count" ]; then
        if [ "$actual_agent_count" -eq "$features_agent_count" ]; then
            pass "Agent count matches FEATURES.md ($actual_agent_count)"
        else
            warn "Agent count mismatch: $actual_agent_count files on disk vs $features_agent_count mentioned in FEATURES.md"
        fi
    else
        warn "Could not find agent count reference in FEATURES.md"
    fi
else
    warn "docs/FEATURES.md not found — skipping agent count comparison"
fi
echo ""

# ── 2. Count actual command files ──────────────────────────────────
echo "=== Checking command counts ==="
actual_cmd_count=$(find "$COMMANDS_DIR" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
echo "INFO: Found $actual_cmd_count command files in claude/commands/"

if [ -f "$FEATURES_MD" ]; then
    # Look for patterns like "13 slash commands" or "N commands"
    features_cmd_count=$(grep -oE '[0-9]+ (slash )?command' "$FEATURES_MD" | head -1 | grep -oE '[0-9]+' || true)
    if [ -n "$features_cmd_count" ]; then
        if [ "$actual_cmd_count" -eq "$features_cmd_count" ]; then
            pass "Command count matches FEATURES.md ($actual_cmd_count)"
        else
            warn "Command count mismatch: $actual_cmd_count files on disk vs $features_cmd_count mentioned in FEATURES.md"
        fi
    else
        warn "Could not find command count reference in FEATURES.md"
    fi
else
    warn "docs/FEATURES.md not found — skipping command count comparison"
fi
echo ""

# ── 3. README.md exists ────────────────────────────────────────────
echo "=== Checking README.md ==="
if [ -f "$README_MD" ]; then
    pass "README.md exists"
else
    fail "README.md not found in repository root"
fi
echo ""

# ── Summary ─────────────────────────────────────────────────────────
echo "Warnings: $WARNINGS"
if [ "$ERRORS" -gt 0 ]; then
    echo "FAILED: $ERRORS error(s) found."
    exit 1
else
    echo "ALL CHECKS PASSED ($WARNINGS warning(s))."
    exit 0
fi
