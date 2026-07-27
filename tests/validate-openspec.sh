#!/usr/bin/env bash
set -euo pipefail

# Validate OpenSpec integration:
#   - The pinned CLI version is consistent across template, conventions doc, and Dockerfile
#   - The committed fixture (spec + change formats our agents write) passes
#     `openspec validate --all --strict` with the pinned CLI
#   - `openspec archive` completes the full loop on a temp copy of the fixture
#
# The CLI checks need Node >= 20 and network access for the first npx download.
# Locally they degrade to warnings; in CI (CI=true) they are hard failures.

OPENSPEC_VERSION="1.6.0"
OPENSPEC_PKG="@fission-ai/openspec"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_ROOT/claude/templates/scrum-team-config.template.md"
CONVENTIONS="$REPO_ROOT/claude/templates/openspec-conventions.md"
DOCKERFILE="$REPO_ROOT/docker/agent-env.Dockerfile"
FIXTURE="$REPO_ROOT/tests/fixtures/openspec-sample"

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

# In CI, environment problems are failures, not warnings
env_problem() {
    if [ "${CI:-false}" = "true" ]; then
        fail "$1"
    else
        warn "$1 (skipping CLI checks locally)"
    fi
}

# ── 1. Pin consistency ──────────────────────────────────────────────
echo ""
echo "=== Checking OpenSpec version pin consistency ==="
PIN="${OPENSPEC_PKG}@${OPENSPEC_VERSION}"

for f in "$TEMPLATE" "$CONVENTIONS" "$DOCKERFILE"; do
    name="${f#$REPO_ROOT/}"
    if [ ! -f "$f" ]; then
        fail "$name: file not found"
        continue
    fi
    if grep -q "$PIN" "$f"; then
        pass "$name pins $PIN"
    else
        fail "$name does not contain the pinned version $PIN"
    fi
    # No OTHER version of the package may appear
    stray=$(grep -oE "${OPENSPEC_PKG}@[0-9][0-9a-zA-Z.-]*" "$f" | grep -v "^${PIN}$" || true)
    if [ -n "$stray" ]; then
        fail "$name contains a stray version pin: $stray"
    fi
done
echo ""

# ── 2. CLI availability ─────────────────────────────────────────────
echo "=== Checking OpenSpec CLI availability ==="
if ! command -v node >/dev/null 2>&1; then
    env_problem "node not found"
elif [ "$(node -e 'console.log(process.versions.node.split(".")[0])')" -lt 20 ]; then
    env_problem "node >= 20 required, found $(node --version)"
elif ! cli_version=$(npx -y "$PIN" --version 2>/dev/null); then
    env_problem "npx -y $PIN --version failed (offline?)"
elif [ "$cli_version" != "$OPENSPEC_VERSION" ]; then
    fail "CLI reported version '$cli_version', expected '$OPENSPEC_VERSION'"
else
    pass "CLI $PIN available"

    # ── 3. Fixture validates strictly ───────────────────────────────
    echo ""
    echo "=== Validating fixture with pinned CLI ==="
    workdir=$(mktemp -d)
    trap 'rm -rf "$workdir"' EXIT
    cp -R "$FIXTURE/openspec" "$workdir/openspec"

    if (cd "$workdir" && npx -y "$PIN" validate --all --strict --no-interactive); then
        pass "fixture passes 'openspec validate --all --strict'"
    else
        fail "fixture failed strict validation — agent-authored formats have drifted from the pinned CLI"
    fi

    # ── 4. Archive completes the loop ───────────────────────────────
    echo ""
    echo "=== Archiving fixture change with pinned CLI ==="
    if (cd "$workdir" && npx -y "$PIN" archive sample-change --yes >/dev/null); then
        if [ -d "$workdir"/openspec/changes/archive/*-sample-change ] \
           && grep -q "Greeting on first visit" "$workdir/openspec/specs/demo/spec.md" \
           && grep -q "pinned to the top" "$workdir/openspec/specs/demo/spec.md"; then
            pass "archive merged ADDED + MODIFIED deltas into living specs"
        else
            fail "archive ran but living specs/archive folder do not look right"
        fi
    else
        fail "openspec archive failed on the fixture change"
    fi
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
