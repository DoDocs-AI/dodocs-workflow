#!/usr/bin/env bash
set -euo pipefail

# Validate cross-references:
#   - subagent_type references point to existing agent files
#   - Command files that reference agent names point to existing agents
#   - File path patterns in agents follow consistent conventions

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_DIR="$REPO_ROOT/claude/agents"
COMMANDS_DIR="$REPO_ROOT/claude/commands"

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

# Build a set of known agent names (without .md extension)
declare -A known_agents
for file in "$AGENTS_DIR"/*.md; do
    name="$(basename "$file" .md)"
    known_agents["$name"]=1
done

# ── 1. Validate subagent_type references in agent files ────────────
echo ""
echo "=== Checking subagent_type references in agent files ==="
found_any=false
for file in "$AGENTS_DIR"/*.md; do
    basename="$(basename "$file")"
    # Look for subagent_type references — extract the value after subagent_type: or subagent_type=
    refs=$(grep -oE 'subagent_type[: ]*"?[a-z0-9_-]+"?' "$file" 2>/dev/null \
        | sed 's/subagent_type[: ]*"*//;s/"$//' || true)
    if [ -n "$refs" ]; then
        found_any=true
        while IFS= read -r ref; do
            [ -z "$ref" ] && continue
            if [ -n "${known_agents[$ref]+x}" ]; then
                pass "$basename: subagent_type '$ref' exists"
            else
                fail "$basename: subagent_type '$ref' references non-existent agent"
            fi
        done <<< "$refs"
    fi
done
if ! $found_any; then
    echo "INFO: No subagent_type references found in agent files (this is OK)."
fi
echo ""

# ── 2. Validate agent references in command files ──────────────────
echo "=== Checking agent references in command files ==="
for file in "$COMMANDS_DIR"/*.md; do
    basename="$(basename "$file")"
    for agent_name in "${!known_agents[@]}"; do
        # Only check for explicit agent dispatch patterns, not casual mentions
        if grep -qE "(agent[: ]+|spawn |dispatch |launch |TaskCreate.*agent.*|subagent[: ]+)\"?${agent_name}\"?" "$file" 2>/dev/null; then
            pass "$basename: references agent '$agent_name' which exists"
        fi
    done
done
echo ""

# ── 3. Validate file path conventions in agent files ───────────────
echo "=== Checking path conventions in agent files ==="
VALID_DOC_PREFIXES="^docs/(plc|features|launch|brainstorm|gtm|production-readiness|e2e-testcases)/$"
for file in "$AGENTS_DIR"/*.md; do
    basename="$(basename "$file")"
    # Extract docs/ path references
    doc_paths=$(grep -oE 'docs/[a-z0-9_-]+/' "$file" 2>/dev/null | sort -u || true)
    if [ -n "$doc_paths" ]; then
        while IFS= read -r path; do
            [ -z "$path" ] && continue
            if echo "$path" | grep -qE "$VALID_DOC_PREFIXES"; then
                pass "$basename: path '$path' follows conventions"
            else
                warn "$basename: path '$path' is not in the standard set"
            fi
        done <<< "$doc_paths"
    fi
done
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
