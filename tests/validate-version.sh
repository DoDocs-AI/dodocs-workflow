#!/usr/bin/env bash
set -euo pipefail

# Validate version consistency:
#   - VERSION file exists and is valid semver
#   - install.sh REPO_URL contains the VERSION
#   - install-opencode.sh REPO_URL contains the VERSION
#   - Both install scripts reference the same version

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$REPO_ROOT/VERSION"
INSTALL_SH="$REPO_ROOT/install.sh"
INSTALL_OPENCODE_SH="$REPO_ROOT/install-opencode.sh"

ERRORS=0

fail() {
    echo "FAIL: $1"
    ERRORS=$((ERRORS + 1))
}

pass() {
    echo "PASS: $1"
}

# ── 1. VERSION file exists and is valid semver ─────────────────────
echo ""
echo "=== Checking VERSION file ==="
if [ ! -f "$VERSION_FILE" ]; then
    fail "VERSION file does not exist"
    echo "FAILED: cannot continue without VERSION file."
    exit 1
fi

VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")

if [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$ ]]; then
    pass "VERSION '$VERSION' is valid semver"
else
    fail "VERSION '$VERSION' is not valid semver"
fi
echo ""

# ── 2. install.sh REPO_URL contains VERSION ────────────────────────
echo "=== Checking install.sh REPO_URL ==="
if [ ! -f "$INSTALL_SH" ]; then
    fail "install.sh not found"
else
    install_repo_url=$(grep 'REPO_URL=' "$INSTALL_SH" | head -1 | sed 's/.*REPO_URL="\([^"]*\)".*/\1/')
    if echo "$install_repo_url" | grep -q "v${VERSION}"; then
        pass "install.sh REPO_URL contains v${VERSION}"
    else
        fail "install.sh REPO_URL does not contain v${VERSION} (found: $install_repo_url)"
    fi
    # Extract version from URL: match vX.Y.Z pattern
    install_version=$(echo "$install_repo_url" | sed -n 's/.*\/v\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*[^/"]*\).*/\1/p')
fi
echo ""

# ── 3. install-opencode.sh REPO_URL contains VERSION ──────────────
echo "=== Checking install-opencode.sh REPO_URL ==="
if [ ! -f "$INSTALL_OPENCODE_SH" ]; then
    fail "install-opencode.sh not found"
else
    opencode_repo_url=$(grep 'REPO_URL=' "$INSTALL_OPENCODE_SH" | head -1 | sed 's/.*REPO_URL="\([^"]*\)".*/\1/')
    if echo "$opencode_repo_url" | grep -q "v${VERSION}"; then
        pass "install-opencode.sh REPO_URL contains v${VERSION}"
    else
        fail "install-opencode.sh REPO_URL does not contain v${VERSION} (found: $opencode_repo_url)"
    fi
    opencode_version=$(echo "$opencode_repo_url" | sed -n 's/.*\/v\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*[^/"]*\).*/\1/p')
fi
echo ""

# ── 4. Both install scripts reference the same version ─────────────
echo "=== Cross-checking install script versions ==="
if [ -n "${install_version:-}" ] && [ -n "${opencode_version:-}" ]; then
    if [ "$install_version" = "$opencode_version" ]; then
        pass "Both install scripts reference the same version: v${install_version}"
    else
        fail "Version mismatch: install.sh has v${install_version}, install-opencode.sh has v${opencode_version}"
    fi
else
    fail "Could not extract version from one or both install scripts"
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
