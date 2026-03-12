#!/usr/bin/env bash
set -euo pipefail

# Validate project structure:
#   - Agent files have required frontmatter fields
#   - All agents/commands listed in install.sh exist on disk
#   - All agent/command files on disk are listed in install.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_DIR="$REPO_ROOT/claude/agents"
COMMANDS_DIR="$REPO_ROOT/claude/commands"
INSTALL_SH="$REPO_ROOT/install.sh"

ERRORS=0

# ── Helper ──────────────────────────────────────────────────────────
fail() {
    echo "FAIL: $1"
    ERRORS=$((ERRORS + 1))
}

pass() {
    echo "PASS: $1"
}

# ── 1. Frontmatter validation ──────────────────────────────────────
echo ""
echo "=== Checking agent frontmatter ==="
for file in "$AGENTS_DIR"/*.md; do
    basename="$(basename "$file")"
    # Extract frontmatter block (between first two --- lines)
    frontmatter=$(sed -n '/^---$/,/^---$/p' "$file")
    if [ -z "$frontmatter" ]; then
        fail "$basename: missing frontmatter block"
        continue
    fi
    for field in name description model tools; do
        if ! echo "$frontmatter" | grep -q "^${field}:"; then
            fail "$basename: missing frontmatter field '$field'"
        fi
    done
done
echo ""

# ── 2. Extract AGENTS array from install.sh ────────────────────────
echo "=== Checking install.sh AGENTS array against disk ==="
# Parse the AGENTS=( ... ) block
install_agents=()
in_agents=false
while IFS= read -r line; do
    if [[ "$line" =~ ^AGENTS=\( ]]; then
        in_agents=true
        continue
    fi
    if $in_agents; then
        if [[ "$line" =~ ^\) ]]; then
            break
        fi
        # Extract quoted agent name
        agent=$(echo "$line" | sed -n 's/.*"\([^"]*\)".*/\1/p')
        if [ -n "$agent" ]; then
            install_agents+=("$agent")
        fi
    fi
done < "$INSTALL_SH"

# Check each agent in install.sh exists on disk
for agent in "${install_agents[@]}"; do
    if [ -f "$AGENTS_DIR/$agent.md" ]; then
        pass "agent '$agent' listed in install.sh exists on disk"
    else
        fail "agent '$agent' listed in install.sh but file '$AGENTS_DIR/$agent.md' not found"
    fi
done
echo ""

# ── 3. Extract COMMANDS array from install.sh ──────────────────────
echo "=== Checking install.sh COMMANDS array against disk ==="
install_commands=()
in_commands=false
while IFS= read -r line; do
    if [[ "$line" =~ ^COMMANDS=\( ]]; then
        in_commands=true
        continue
    fi
    if $in_commands; then
        if [[ "$line" =~ ^\) ]]; then
            break
        fi
        cmd=$(echo "$line" | sed -n 's/.*"\([^"]*\)".*/\1/p')
        if [ -n "$cmd" ]; then
            install_commands+=("$cmd")
        fi
    fi
done < "$INSTALL_SH"

for cmd in "${install_commands[@]}"; do
    if [ -f "$COMMANDS_DIR/$cmd.md" ]; then
        pass "command '$cmd' listed in install.sh exists on disk"
    else
        fail "command '$cmd' listed in install.sh but file '$COMMANDS_DIR/$cmd.md' not found"
    fi
done
echo ""

# ── 4. Reverse check: every agent file on disk is in install.sh ────
echo "=== Reverse check: agent files on disk listed in install.sh ==="
for file in "$AGENTS_DIR"/*.md; do
    name="$(basename "$file" .md)"
    found=false
    for a in "${install_agents[@]}"; do
        if [ "$a" = "$name" ]; then
            found=true
            break
        fi
    done
    if $found; then
        pass "agent file '$name.md' is listed in install.sh"
    else
        fail "agent file '$name.md' exists on disk but is NOT listed in install.sh AGENTS array"
    fi
done
echo ""

# ── 5. Reverse check: every command file on disk is in install.sh ──
echo "=== Reverse check: command files on disk listed in install.sh ==="
for file in "$COMMANDS_DIR"/*.md; do
    name="$(basename "$file" .md)"
    found=false
    for c in "${install_commands[@]}"; do
        if [ "$c" = "$name" ]; then
            found=true
            break
        fi
    done
    if $found; then
        pass "command file '$name.md' is listed in install.sh"
    else
        fail "command file '$name.md' exists on disk but is NOT listed in install.sh COMMANDS array"
    fi
done
echo ""

# ── Summary ─────────────────────────────────────────────────────────
if [ "$ERRORS" -gt 0 ]; then
    echo "FAILED: $ERRORS error(s) found."
    exit 1
else
    echo "ALL CHECKS PASSED."
    exit 0
fi
