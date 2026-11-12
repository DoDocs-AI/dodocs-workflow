#!/usr/bin/env bash
set -euo pipefail

# Validate the control point (`dw`) tooling:
#   - control/dw exists and is executable
#   - the unittest suite in tests/control passes under python3, and also under
#     /usr/bin/python3 when that is a different interpreter

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ERRORS=0

fail() {
    echo "FAIL: $1"
    ERRORS=$((ERRORS + 1))
}

pass() {
    echo "PASS: $1"
}

echo ""
echo "=== Checking control/dw ==="
if [ -x control/dw ]; then
    pass "control/dw is executable"
else
    fail "control/dw is missing or not executable"
fi

run_suite() {
    local py="$1"
    if "$py" -m unittest discover -s tests/control >/dev/null 2>/tmp/dw-validate.$$; then
        pass "unittest suite passes under $py ($("$py" --version 2>&1))"
    else
        fail "unittest suite fails under $py"
        sed 's/^/    /' /tmp/dw-validate.$$
    fi
    rm -f /tmp/dw-validate.$$
}

echo ""
echo "=== Running control unit tests ==="
run_suite python3
if [ -f /usr/bin/python3 ] && ! [ /usr/bin/python3 -ef "$(command -v python3)" ]; then
    run_suite /usr/bin/python3
fi

echo ""
if [ "$ERRORS" -gt 0 ]; then
    echo "FAILED: $ERRORS error(s)"
    exit 1
fi
echo "All control checks passed."
